#!/usr/bin/env python3
"""Generate the IoT Support deployed-architecture artifact.

This is the repo-side generator for the *generated* `iotsupport-app` producer.
It projects the physical ESP32 device fleet (read from the prd API) into the
federated Architecture-as-Code model, resolving every realized dependency edge
of each device's firmware «SoftwareProduct».

Pipeline (CI / Jenkinsfile.architecture `Generate` stage):

    1. Fetch the published federated dataset (HTTPS).
    2. Fetch GET /api/pipeline/fleet-projection (client-credentials token).
    3. Load docs/architecture/firmware-products.yaml (code -> product UUID).
    4. Resolve once-per-build cap providers (iam, pub-sub-broker) and concrete
       svc providers (home-assistant-mqtt, calendar-support, infra-statistics,
       iotsupport-api, intercom) to their running prd instances.
    5. Per device: mint device:/ss: uuid5 elements + Specialization/Assignment/
       Serving/Aggregation edges; group ss: instances per firmware.
    6. Emit the YAML envelope (producer: iotsupport-app, no per-element producer).

Determinism: all element ids are uuid5 from a private IoT Support namespace
keyed on the immutable Device.key / firmware code, so re-runs are byte-identical.

The module is import-safe: all I/O lives in `main()`; the resolution and
emission logic are pure functions exercised by tools/tests.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import yaml  # type: ignore[import-untyped]

# Private IoT Support uuid5 namespace. Owned by THIS generator so per-device
# ids never collide with other producers' device: elements nor with this
# repo's hand-authored artifact. Do not change (would re-key every element).
IOTSUPPORT_NS = uuid.UUID("b3f2c1a0-7d4e-5b6a-9c8d-1e2f3a4b5c6d")

SCHEMA_VERSION = "0.1"
PRODUCER = "iotsupport-app"

DEFAULT_DATASET_URL = "https://architecture.webathome.org/api/dataset"


# --------------------------------------------------------------------------- #
# Dataset helpers
# --------------------------------------------------------------------------- #

def _hint(element_id: str) -> str:
    """Return the human hint portion of an element id (drop the ,uuid suffix)."""
    return element_id.split(",", 1)[0] if "," in element_id else element_id


class Dataset:
    """Indexed view over a published federated dataset."""

    ELEMENT_CATEGORIES = (
        "nodes",
        "devices",
        "systemSoftware",
        "applicationComponents",
        "applicationServices",
        "applicationInterfaces",
        "technologyServices",
        "technologyInterfaces",
        "capabilities",
        "businessServices",
        "groupings",
    )

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.by_id: dict[str, dict[str, Any]] = {}
        self.by_hint: dict[str, list[dict[str, Any]]] = {}
        for cat in self.ELEMENT_CATEGORIES:
            for element in raw.get(cat, []):
                self.by_id[element["id"]] = element
                self.by_hint.setdefault(_hint(element["id"]), []).append(element)
        self.relations: list[dict[str, Any]] = raw.get("relations", [])

    def element_by_hint(self, hint: str) -> dict[str, Any]:
        """Return the single element whose id-hint equals `hint` (fail loud)."""
        matches = self.by_hint.get(hint, [])
        if not matches:
            raise GeneratorError(f"no dataset element with hint {hint!r}")
        if len(matches) > 1:
            raise GeneratorError(
                f"ambiguous hint {hint!r}: {[m['id'] for m in matches]}"
            )
        return matches[0]

    def realizers(self, target_id: str) -> list[dict[str, Any]]:
        """Elements that Realize the given target id."""
        return [
            self.by_id[r["source"]]
            for r in self.relations
            if r.get("type") == "Realization"
            and r.get("target") == target_id
            and r.get("source") in self.by_id
        ]

    def specializers(self, target_id: str) -> list[dict[str, Any]]:
        """Elements that Specialize the given target id."""
        return [
            self.by_id[r["source"]]
            for r in self.relations
            if r.get("type") == "Specialization"
            and r.get("target") == target_id
            and r.get("source") in self.by_id
        ]

    def associations_from(self, source_id: str) -> list[str]:
        """Target id-hints of Association edges sourced from `source_id`."""
        return [
            _hint(r["target"])
            for r in self.relations
            if r.get("type") == "Association" and r.get("source") == source_id
        ]


class GeneratorError(Exception):
    """Fatal generator error — aborts the build (no partial artifact)."""


# --------------------------------------------------------------------------- #
# Provider resolution
# --------------------------------------------------------------------------- #

def _is_product(element: dict[str, Any]) -> bool:
    return element.get("stereotype") == "SoftwareProduct"


def _host_of(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(url).hostname


def _hosts_set(element: dict[str, Any]) -> set[str]:
    """Hosts declared on an element's stats (comma-joined string or list)."""
    stats = element.get("stats") or {}
    raw = stats.get("hosts")
    out: set[str] = set()
    if isinstance(raw, str):
        out.update(h.strip() for h in raw.split(",") if h.strip())
    elif isinstance(raw, list):
        out.update(str(h).strip() for h in raw if str(h).strip())
    url = stats.get("url")
    if isinstance(url, str) and url.strip():
        out.add(url.strip())
    return out


def resolve_capability_provider(
    dataset: Dataset, cap_hint: str, fleet_url: str | None
) -> dict[str, Any]:
    """Resolve a substitutable capability to its single prd realizer instance.

    Candidate rule (relation-grounded): elements that `Realization→cap`,
    DROPPING `stereotype: SoftwareProduct` realizers (product-level), then
    filtered to `environment == "prd"` (strict equality, so env-unset logical
    realizers are excluded by design). If exactly one survives, that is the
    provider. If more than one, tiebreak by the fleet URL host; assert exactly
    one survivor or fail loud.
    """
    cap = dataset.element_by_hint(cap_hint)
    realizers = [r for r in dataset.realizers(cap["id"]) if not _is_product(r)]
    prd = [r for r in realizers if r.get("environment") == "prd"]

    if len(prd) == 1:
        return prd[0]

    if len(prd) == 0:
        raise GeneratorError(
            f"capability {cap_hint} has no prd instance realizer "
            f"(candidates: {[_hint(r['id']) for r in realizers]})"
        )

    # >1 prd realizer: tiebreak by fleet URL host.
    host = _host_of(fleet_url)
    if host is None:
        raise GeneratorError(
            f"capability {cap_hint} has {len(prd)} prd realizers and no fleet "
            f"URL to tiebreak: {[_hint(r['id']) for r in prd]}"
        )
    # Bridge: a host-bearing svc:/if: that shares the realizer's release/hint
    # stem carries the host (no relation links them). Match host -> realizer by
    # confirming a host-bearing element shares the realizer's leading stem.
    matched = _tiebreak_by_host(dataset, prd, host)
    if matched is None:
        raise GeneratorError(
            f"capability {cap_hint} host tiebreak failed for host {host!r} "
            f"among {[_hint(r['id']) for r in prd]}"
        )
    return matched


def _tiebreak_by_host(
    dataset: Dataset, candidates: list[dict[str, Any]], host: str
) -> dict[str, Any] | None:
    """Pick the candidate realizer whose naming stem owns `host`.

    The host-bearing element (svc:/if:) is linked to the realizing ss: only by
    a shared release/hint stem, NOT by a relation edge. We find every element
    declaring `host`, then match a candidate realizer that shares a hint stem
    with one of them. Returns the single matching candidate or None.
    """
    host_owners = [
        element
        for element in dataset.by_id.values()
        if host in _hosts_set(element)
    ]
    if not host_owners:
        return None

    matches: list[dict[str, Any]] = []
    for cand in candidates:
        cand_stem = _hint(cand["id"]).split(":", 1)[-1]
        for owner in host_owners:
            owner_stem = _hint(owner["id"]).split(":", 1)[-1]
            shared = _shared_prefix_tokens(cand_stem, owner_stem)
            if shared:
                matches.append(cand)
                break

    if len(matches) == 1:
        return matches[0]
    return None


def _shared_prefix_tokens(a: str, b: str) -> bool:
    """True if one hyphen-tokenized stem is a leading-token prefix of the other.

    Matching on the full shorter token sequence (rather than only the first
    token) keeps the host bridge precise: e.g. the realizer stem
    ``keycloak-prd-keycloak-keycloak`` bridges to the host owner stem
    ``keycloak-prd-keycloak`` because every owner token matches the realizer's
    leading tokens. A spurious sibling that merely shares ``keycloak`` as its
    first token (e.g. ``keycloak-dev-...``) would not bridge, reducing the
    chance of mis-bridging should a cap ever gain a second prd realizer.
    """
    at = a.split("-")
    bt = b.split("-")
    if not at or not bt:
        return False
    shorter, longer = (at, bt) if len(at) <= len(bt) else (bt, at)
    return longer[: len(shorter)] == shorter


def resolve_service_provider(dataset: Dataset, svc_hint: str) -> dict[str, Any] | None:
    """Resolve a concrete `svc:` to its running prd instance.

    Three realizer shapes (see plan §5 step 4):

      (a) svc realized directly by a prd instance (e.g. svc:home-assistant-mqtt
          via ss:home-assistant-prd). Take the prd, non-product realizer.
      (b) svc realized by a product only (e.g. svc:iotsupport-api via
          app:iotsupport-app). Descend to the product's prd Specializer. When
          several specialize (iotsupport-api has 3), discriminate by
          stats.workload / container == the bare svc stem.
      (c) product realizer with no prd instance (svc:intercom). Returns None ->
          the caller SKIPS that one Serving edge and warns.
    """
    svc = dataset.element_by_hint(svc_hint)
    realizers = dataset.realizers(svc["id"])

    candidates: list[dict[str, Any]] = []

    for realizer in realizers:
        if not _is_product(realizer):
            # Shape (a): the realizer is itself a deployed instance.
            if realizer.get("environment") == "prd":
                candidates.append(realizer)
        else:
            # Shape (b): descend to the product's prd specializers.
            specializers = [
                s for s in dataset.specializers(realizer["id"])
                if s.get("environment") == "prd"
            ]
            if len(specializers) > 1:
                specializers = _discriminate_workload(specializers, svc_hint)
            candidates.extend(specializers)

    # De-dup by id (a svc may be reachable via both a prd instance and product).
    seen: dict[str, dict[str, Any]] = {}
    for cand in candidates:
        seen[cand["id"]] = cand
    unique = list(seen.values())

    if len(unique) == 0:
        # Shape (c): no deployed provider instance.
        return None
    if len(unique) > 1:
        raise GeneratorError(
            f"service {svc_hint} resolved to {len(unique)} prd instances: "
            f"{[_hint(c['id']) for c in unique]}"
        )
    return unique[0]


def _discriminate_workload(
    specializers: list[dict[str, Any]], svc_hint: str
) -> list[dict[str, Any]]:
    """Pick the main-workload specializer (exclude cronjob/setup instances).

    The discriminator is stats.workload / stats.container equal to the bare
    svc stem (e.g. svc:iotsupport-api -> workload/container "iotsupport"),
    NOT environment (all are prd).
    """
    stem = svc_hint.split(":", 1)[-1]
    # svc:iotsupport-api -> "iotsupport"; svc:calendar-support -> "calendar-support".
    target = stem[:-4] if stem.endswith("-api") else stem
    matched = [
        s for s in specializers
        if (s.get("stats") or {}).get("workload") == target
        or (s.get("stats") or {}).get("container") == f"{target}-app"
    ]
    return matched if matched else specializers


# --------------------------------------------------------------------------- #
# Artifact emission
# --------------------------------------------------------------------------- #

def _uuid5(prefix: str, key: str) -> str:
    """Stable uuid5 for an element keyed on prefix + natural key."""
    return str(uuid.uuid5(IOTSUPPORT_NS, f"{prefix}:{key}"))


def _relation(rel_type: str, source: str, target: str) -> dict[str, Any]:
    """Build a relation with a deterministic uuid5-based id.

    The id is keyed on (type, source, target) so re-runs are byte-identical and
    distinct edges never collide. Matches the relations schema pattern
    ``rel:<uuid>``.
    """
    rel_uuid = uuid.uuid5(IOTSUPPORT_NS, f"rel:{rel_type}:{source}:{target}")
    return {
        "id": f"rel:{rel_uuid}",
        "source": source,
        "target": target,
        "type": rel_type,
    }


def _date_of(created_at: str) -> str:
    """Date portion (YYYY-MM-DD) of an ISO timestamp.

    The live projection API serializes ``created_at`` from a naive (no-tz)
    DateTime column, so it emits offset-less ISO timestamps like
    ``2026-03-14T09:21:07``. Some sources (and older fixtures) instead append a
    trailing ``Z``. ``datetime.fromisoformat`` accepts both naive and
    offset-bearing strings, and (3.11+) understands ``Z`` directly, but we
    normalize a trailing ``Z`` defensively so the behavior is identical
    regardless of which shape we receive. We only take the date, so the
    timezone (or its absence) does not shift the result for these UTC values.
    """
    normalized = created_at[:-1] + "+00:00" if created_at.endswith("Z") else created_at
    return datetime.fromisoformat(normalized).date().isoformat()


def generate_artifact(
    dataset: Dataset,
    projection: dict[str, Any],
    firmware_products: dict[str, str],
    *,
    warn: Any = None,
) -> dict[str, Any]:
    """Build the deployed-architecture artifact dict (pure; no I/O).

    Args:
        dataset: indexed published dataset.
        projection: GET /api/pipeline/fleet-projection body.
        firmware_products: code -> firmware product UUID map.
        warn: optional callable(str) for non-fatal warnings (defaults to stderr).

    Returns:
        The artifact dict ready for YAML emission.

    Raises:
        GeneratorError: on unmapped model code or unresolvable cap/svc provider.
    """
    if warn is None:
        def warn(msg: str) -> None:
            print(f"WARNING: {msg}", file=sys.stderr)

    fleet = projection.get("fleet", {})
    devices = projection.get("devices", [])

    # Resolve once-per-build providers, keyed by the Association target hint.
    cap_providers = {
        "cap:iam": resolve_capability_provider(
            dataset, "cap:iam", fleet.get("oidc_issuer_url")
        ),
        "cap:pub-sub-broker": resolve_capability_provider(
            dataset, "cap:pub-sub-broker", fleet.get("mqtt_url")
        ),
    }

    # Discover concrete svc: targets referenced by any firmware in the fleet,
    # then resolve each once. None means "skip Serving edge + warn" (shape c).
    svc_targets: set[str] = set()
    for device in devices:
        code = device["model_code"]
        product_uuid = firmware_products.get(code)
        if product_uuid is None:
            raise GeneratorError(
                f"device {device['key']!r} has model code {code!r} not present "
                f"in firmware-products.yaml — add its firmware product UUID"
            )
        for target in dataset.associations_from(_full_id(dataset, product_uuid)):
            if target.startswith("svc:"):
                svc_targets.add(target)

    svc_providers: dict[str, dict[str, Any] | None] = {}
    for svc_hint in sorted(svc_targets):
        provider = resolve_service_provider(dataset, svc_hint)
        svc_providers[svc_hint] = provider
        if provider is None:
            warn(
                f"service {svc_hint} has no deployed prd instance; its Serving "
                f"edges are skipped (expected/transient until it deploys)"
            )

    device_elements: list[dict[str, Any]] = []
    ss_elements: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    # firmware code -> {introduced(min date), member ss: ids}
    groupings: dict[str, dict[str, Any]] = {}

    for device in sorted(devices, key=lambda d: d["key"]):
        key = device["key"]
        code = device["model_code"]
        firmware_version = device.get("firmware_version")
        product_uuid = firmware_products[code]
        product_full_id = _full_id(dataset, product_uuid)
        product_hint = _hint(product_full_id)
        fw_hint = product_hint.split(":", 1)[-1]  # e.g. "calendar-display"
        introduced = _date_of(device["created_at"])

        device_id = f"device:{fw_hint}-{key},{_uuid5('device', key)}"
        ss_id = f"ss:{fw_hint}-{key},{_uuid5('ss', key)}"

        device_elements.append({
            "id": device_id,
            "label": device.get("device_name") or key,
            "summary": f"ESP32 device {key} running {fw_hint} firmware.",
            "introduced": introduced,
            "lifecycle": "active",
            "stats": _device_stats(code, firmware_version),
        })

        ss_elements.append({
            "id": ss_id,
            "label": f"{fw_hint} @ {key}",
            "summary": f"{fw_hint} firmware instance running on device {key}.",
            "introduced": introduced,
            "lifecycle": "active",
        })

        # device runs the firmware instance; instance specializes the product.
        relations.append(_relation("Assignment", device_id, ss_id))
        relations.append(_relation("Specialization", ss_id, product_full_id))

        # One Serving edge per realized logical Association on the firmware.
        for target in dataset.associations_from(product_full_id):
            provider = _provider_for(target, cap_providers, svc_providers)
            if provider is None:
                # Skipped svc (shape c) — already warned once.
                continue
            relations.append(_relation("Serving", provider["id"], ss_id))

        # Per-firmware grouping (legibility). introduced = min over members.
        grouping = groupings.setdefault(
            fw_hint, {"introduced": introduced, "members": []}
        )
        grouping["members"].append(ss_id)
        if introduced < grouping["introduced"]:
            grouping["introduced"] = introduced

    grouping_elements: list[dict[str, Any]] = []
    for fw_hint in sorted(groupings):
        grp = groupings[fw_hint]
        grp_id = f"grp:{fw_hint},{_uuid5('grp', fw_hint)}"
        grouping_elements.append({
            "id": grp_id,
            "label": f"{fw_hint} fleet",
            "summary": f"All deployed {fw_hint} firmware instances.",
            "introduced": grp["introduced"],
            "lifecycle": "active",
        })
        for ss_id in grp["members"]:
            relations.append(_relation("Aggregation", grp_id, ss_id))

    artifact: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "producer": PRODUCER,
    }
    if device_elements:
        artifact["devices"] = device_elements
    if ss_elements:
        artifact["systemSoftware"] = ss_elements
    if grouping_elements:
        artifact["groupings"] = grouping_elements
    if relations:
        artifact["relations"] = relations
    return artifact


def _device_stats(code: str, firmware_version: str | None) -> dict[str, str]:
    """Identity-fenced stats: only model + firmware version."""
    stats = {"model": code}
    if firmware_version is not None:
        stats["firmware"] = firmware_version
    return stats


def _provider_for(
    target_hint: str,
    cap_providers: dict[str, dict[str, Any]],
    svc_providers: dict[str, dict[str, Any] | None],
) -> dict[str, Any] | None:
    """Map an Association target hint to its resolved provider instance."""
    if target_hint in cap_providers:
        return cap_providers[target_hint]
    if target_hint in svc_providers:
        return svc_providers[target_hint]
    raise GeneratorError(f"no resolved provider for Association target {target_hint!r}")


def _full_id(dataset: Dataset, product_uuid: str) -> str:
    """Find the full `hint,uuid` id for a firmware product by its UUID."""
    for element_id in dataset.by_id:
        if element_id.endswith(f",{product_uuid}"):
            return element_id
    raise GeneratorError(
        f"firmware product UUID {product_uuid} not found in the published dataset"
    )


# --------------------------------------------------------------------------- #
# I/O wiring (CI entrypoint)
# --------------------------------------------------------------------------- #

def load_firmware_products(path: Path) -> dict[str, str]:
    """Load code -> product UUID map from the committed annotation file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    products = (data or {}).get("products") or {}
    return {str(k): str(v) for k, v in products.items()}


def fetch_dataset(url: str) -> Dataset:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return Dataset(resp.json())


def fetch_token(token_url: str, client_id: str, client_secret: str) -> str:
    resp = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return str(resp.json()["access_token"])


def fetch_projection(api_url: str, token: str) -> dict[str, Any]:
    resp = requests.get(
        f"{api_url.rstrip('/')}/api/pipeline/fleet-projection",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return dict(resp.json())


def dump_yaml(artifact: dict[str, Any]) -> str:
    """Serialize the artifact deterministically (no key sorting, block style)."""
    return str(yaml.safe_dump(artifact, sort_keys=False, default_flow_style=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="docs/architecture/deployed-architecture.yaml",
        help="output path for the generated artifact",
    )
    parser.add_argument(
        "--firmware-products",
        default="docs/architecture/firmware-products.yaml",
        help="path to the code->product UUID annotation file",
    )
    parser.add_argument(
        "--dataset-url",
        default=os.environ.get("ARCHITECTURE_DATASET_URL", DEFAULT_DATASET_URL),
        help="published federated dataset URL",
    )
    parser.add_argument(
        "--dataset-file",
        default=None,
        help="read the dataset from a local JSON file instead of fetching",
    )
    parser.add_argument(
        "--projection-file",
        default=None,
        help="read the projection from a local JSON file instead of fetching",
    )
    args = parser.parse_args(argv)

    try:
        # Dataset: file or HTTPS.
        if args.dataset_file:
            with open(args.dataset_file, encoding="utf-8") as f:
                dataset = Dataset(json.load(f))
        else:
            dataset = fetch_dataset(args.dataset_url)

        # Projection: file or prd API via client-credentials token.
        if args.projection_file:
            with open(args.projection_file, encoding="utf-8") as f:
                projection = json.load(f)
        else:
            api_url = _require_env("IOTSUPPORT_API_URL")
            token = fetch_token(
                _require_env("IOTSUPPORT_TOKEN_URL"),
                _require_env("IOTSUPPORT_CLIENT_ID"),
                _require_env("IOTSUPPORT_CLIENT_SECRET"),
            )
            projection = fetch_projection(api_url, token)

        firmware_products = load_firmware_products(Path(args.firmware_products))
        artifact = generate_artifact(dataset, projection, firmware_products)

    except GeneratorError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print(f"ERROR: fetch failed: {e}", file=sys.stderr)
        return 1

    Path(args.output).write_text(dump_yaml(artifact), encoding="utf-8")
    print(
        f"Wrote {args.output}: {len(artifact.get('devices', []))} devices, "
        f"{len(artifact.get('relations', []))} relations",
        file=sys.stderr,
    )
    return 0


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise GeneratorError(f"required environment variable {name} is not set")
    return value


if __name__ == "__main__":
    sys.exit(main())
