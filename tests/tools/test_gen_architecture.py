"""Unit tests for tools/gen-architecture.py (generated producer)."""

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_module() -> Any:
    """Import the hyphenated generator module by path."""
    spec = importlib.util.spec_from_file_location(
        "gen_architecture", _REPO_ROOT / "tools" / "gen-architecture.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


genarch = _load_module()


@pytest.fixture
def dataset() -> Any:
    raw = json.loads((_FIXTURES / "architecture_dataset.json").read_text())
    return genarch.Dataset(raw)


@pytest.fixture
def raw_dataset() -> dict[str, Any]:
    return json.loads((_FIXTURES / "architecture_dataset.json").read_text())


@pytest.fixture
def projection() -> dict[str, Any]:
    return json.loads((_FIXTURES / "architecture_projection.json").read_text())


@pytest.fixture
def firmware_products() -> dict[str, str]:
    return genarch.load_firmware_products(
        _REPO_ROOT / "docs" / "architecture" / "firmware-products.yaml"
    )


def _hint(eid: str) -> str:
    return eid.split(",", 1)[0] if "," in eid else eid


def _silent(_msg: str) -> None:
    pass


class TestProviderResolution:
    """Capability and concrete-service provider resolution shapes."""

    def test_cap_iam_picks_prd_instance(self, dataset: Any) -> None:
        """prd instance chosen; dev + env-unset product realizers dropped."""
        provider = genarch.resolve_capability_provider(
            dataset, "cap:iam",
            "https://auth.ginbov.nl/realms/iot/protocol/openid-connect/token",
        )
        assert _hint(provider["id"]) == "ss:keycloak-prd-keycloak-keycloak"

    def test_cap_pub_sub_picks_prd_instance(self, dataset: Any) -> None:
        provider = genarch.resolve_capability_provider(
            dataset, "cap:pub-sub-broker", "mqtt://mosquitto.home:1883"
        )
        assert _hint(provider["id"]) == "ss:mosquitto-mosquitto-mosquitto"

    def test_svc_home_assistant_mqtt_shape_a(self, dataset: Any) -> None:
        """svc realized by a prd instance + a product -> prd instance chosen."""
        provider = genarch.resolve_service_provider(dataset, "svc:home-assistant-mqtt")
        assert provider is not None
        assert _hint(provider["id"]) == "ss:home-assistant-prd"

    def test_svc_calendar_support_shape_b(self, dataset: Any) -> None:
        """svc realized by a product only -> single prd specializer chosen."""
        provider = genarch.resolve_service_provider(dataset, "svc:calendar-support")
        assert provider is not None
        assert _hint(provider["id"]) == (
            "app:calendar-support-calendar-support-calendar-support-app"
        )

    def test_svc_iotsupport_api_workload_discriminator(self, dataset: Any) -> None:
        """Three specializers -> the iotsupport main workload is selected."""
        provider = genarch.resolve_service_provider(dataset, "svc:iotsupport-api")
        assert provider is not None
        assert _hint(provider["id"]) == "app:iot-iotsupport-iotsupport-app"

    def test_svc_intercom_shape_c_returns_none(self, dataset: Any) -> None:
        """Product realizer with no prd instance -> None (caller skips edge)."""
        provider = genarch.resolve_service_provider(dataset, "svc:intercom")
        assert provider is None

    def test_cap_two_prd_realizers_ambiguous_host_fails(
        self, raw_dataset: dict[str, Any]
    ) -> None:
        """Two prd realizers that both stem-bridge the host -> fail loud.

        The host owner ``svc:keycloak-prd-keycloak`` (auth.ginbov.nl) only
        bridges a realizer whose stem has ``keycloak-prd-keycloak`` as a leading
        token prefix. A genuine second prd realizer sharing that full prefix
        (e.g. a replica) makes the bridge ambiguous, so the assert-exactly-one
        guard must raise rather than guess.
        """
        mutated = copy.deepcopy(raw_dataset)
        # Add a second prd realizer that shares the host owner's full stem
        # prefix, so the host bridge cannot disambiguate between the two.
        replica = copy.deepcopy(
            next(
                e for e in mutated["systemSoftware"]
                if _hint(e["id"]) == "ss:keycloak-prd-keycloak-keycloak"
            )
        )
        replica["id"] = (
            "ss:keycloak-prd-keycloak-replica,"
            "ffffffff-1256-58ba-85d9-64d7866388c4"
        )
        mutated["systemSoftware"].append(replica)
        # Realize cap:iam from the replica too.
        mutated["relations"].append(
            {
                "id": "rel:ffffffff-0000-0000-0000-000000000001",
                "source": replica["id"],
                "target": next(
                    c["id"] for c in mutated["capabilities"]
                    if _hint(c["id"]) == "cap:iam"
                ),
                "type": "Realization",
            }
        )
        dataset = genarch.Dataset(mutated)
        with pytest.raises(genarch.GeneratorError):
            genarch.resolve_capability_provider(
                dataset, "cap:iam",
                "https://auth.ginbov.nl/realms/iot/protocol/openid-connect/token",
            )

    def test_cap_dev_sibling_does_not_mis_bridge(
        self, raw_dataset: dict[str, Any]
    ) -> None:
        """A prd-promoted dev sibling sharing only the first token is excluded.

        ``ss:keycloak-dev-keycloak-keycloak`` shares only the leading ``keycloak``
        token with the host owner ``svc:keycloak-prd-keycloak``; the tightened
        prefix match must NOT bridge it, so cap:iam still resolves uniquely to
        the prd instance.
        """
        mutated = copy.deepcopy(raw_dataset)
        for element in mutated["systemSoftware"]:
            if _hint(element["id"]) == "ss:keycloak-dev-keycloak-keycloak":
                element["environment"] = "prd"
        dataset = genarch.Dataset(mutated)
        provider = genarch.resolve_capability_provider(
            dataset, "cap:iam",
            "https://auth.ginbov.nl/realms/iot/protocol/openid-connect/token",
        )
        assert _hint(provider["id"]) == "ss:keycloak-prd-keycloak-keycloak"


class TestArtifactGeneration:
    """Whole-artifact emission against the fixture fleet."""

    def test_per_device_elements_and_edges(
        self, dataset: Any, projection: dict[str, Any], firmware_products: dict[str, str]
    ) -> None:
        artifact = genarch.generate_artifact(
            dataset, projection, firmware_products, warn=_silent
        )

        # 4 devices -> 4 device: + 4 ss: instances.
        assert len(artifact["devices"]) == 4
        assert len(artifact["systemSoftware"]) == 4

        # Two firmware families present (calendar-display, doorbell-receiver,
        # intercom) -> one grouping each.
        grp_hints = {_hint(g["id"]) for g in artifact["groupings"]}
        assert grp_hints == {
            "grp:calendar-display", "grp:doorbell-receiver", "grp:intercom"
        }

        # Locate the calendar device aa11bb22 and verify its full edge set.
        ss_cal = next(
            s for s in artifact["systemSoftware"]
            if _hint(s["id"]) == "ss:calendar-display-aa11bb22"
        )
        ss_id = ss_cal["id"]
        rels = artifact["relations"]

        # Assignment device -> ss
        assert any(
            r["type"] == "Assignment" and r["target"] == ss_id
            and _hint(r["source"]) == "device:calendar-display-aa11bb22"
            for r in rels
        )
        # Specialization ss -> product
        assert any(
            r["type"] == "Specialization" and r["source"] == ss_id
            and _hint(r["target"]) == "ss:calendar-display"
            for r in rels
        )
        # Serving edges: iam, pub-sub, calendar-support, iotsupport-api (4).
        serving_sources = {
            _hint(r["source"]) for r in rels
            if r["type"] == "Serving" and r["target"] == ss_id
        }
        assert serving_sources == {
            "ss:keycloak-prd-keycloak-keycloak",
            "ss:mosquitto-mosquitto-mosquitto",
            "app:calendar-support-calendar-support-calendar-support-app",
            "app:iot-iotsupport-iotsupport-app",
        }
        # Aggregation grp -> ss
        assert any(
            r["type"] == "Aggregation" and r["target"] == ss_id
            and _hint(r["source"]) == "grp:calendar-display"
            for r in rels
        )

    def test_intercom_serving_edge_skipped_with_warning(
        self, dataset: Any, projection: dict[str, Any], firmware_products: dict[str, str]
    ) -> None:
        """svc:intercom has no prd instance: edge skipped, warning emitted."""
        warnings: list[str] = []
        artifact = genarch.generate_artifact(
            dataset, projection, firmware_products, warn=warnings.append
        )
        assert any("svc:intercom" in w for w in warnings)

        ss_intercom = next(
            s for s in artifact["systemSoftware"]
            if _hint(s["id"]) == "ss:intercom-gg77hh88"
        )
        ss_id = ss_intercom["id"]
        serving_sources = {
            _hint(r["source"]) for r in artifact["relations"]
            if r["type"] == "Serving" and r["target"] == ss_id
        }
        # No svc:intercom provider, but the other 4 edges still resolve
        # (intercom firmware: iam, pub-sub, home-assistant-mqtt, iotsupport-api).
        assert "svc:intercom" not in serving_sources
        assert serving_sources == {
            "ss:keycloak-prd-keycloak-keycloak",
            "ss:mosquitto-mosquitto-mosquitto",
            "ss:home-assistant-prd",
            "app:iot-iotsupport-iotsupport-app",
        }

    @pytest.mark.parametrize(
        "created_at",
        [
            # Naive (no-tz) shape the live projection API actually emits, since
            # Device.created_at is a tz-naive DateTime serialized via
            # model_dump(mode="json").
            "2026-03-14T09:21:07",
            "2026-03-14T09:21:07.123456",
            # Legacy/alternative 'Z'-suffixed UTC shape.
            "2026-03-14T09:21:07Z",
            # Explicit offset shape.
            "2026-03-14T09:21:07+00:00",
        ],
    )
    def test_date_of_handles_naive_and_tz_timestamps(self, created_at: str) -> None:
        """_date_of yields the same date for naive, Z-suffixed, and offset shapes."""
        assert genarch._date_of(created_at) == "2026-03-14"

    def test_introduced_dates(
        self, dataset: Any, projection: dict[str, Any], firmware_products: dict[str, str]
    ) -> None:
        """device/ss introduced = date(created_at); grouping = min over members."""
        artifact = genarch.generate_artifact(
            dataset, projection, firmware_products, warn=_silent
        )

        dev_aa = next(
            d for d in artifact["devices"]
            if _hint(d["id"]) == "device:calendar-display-aa11bb22"
        )
        assert dev_aa["introduced"] == "2026-03-14"

        ss_aa = next(
            s for s in artifact["systemSoftware"]
            if _hint(s["id"]) == "ss:calendar-display-aa11bb22"
        )
        assert ss_aa["introduced"] == "2026-03-14"

        # calendar-display has two members: aa11bb22 (2026-03-14) and
        # ee55ff66 (2026-01-05) -> grouping introduced = min = 2026-01-05.
        grp_cal = next(
            g for g in artifact["groupings"]
            if _hint(g["id"]) == "grp:calendar-display"
        )
        assert grp_cal["introduced"] == "2026-01-05"

    def test_null_firmware_omits_firmware_stat(
        self, dataset: Any, projection: dict[str, Any], firmware_products: dict[str, str]
    ) -> None:
        artifact = genarch.generate_artifact(
            dataset, projection, firmware_products, warn=_silent
        )
        dev_doorbell = next(
            d for d in artifact["devices"]
            if _hint(d["id"]) == "device:doorbell-receiver-cc33dd44"
        )
        assert dev_doorbell["stats"] == {"model": "doorbell_receiver"}
        assert "firmware" not in dev_doorbell["stats"]

    def test_no_per_element_producer(
        self, dataset: Any, projection: dict[str, Any], firmware_products: dict[str, str]
    ) -> None:
        artifact = genarch.generate_artifact(
            dataset, projection, firmware_products, warn=_silent
        )
        assert artifact["producer"] == "iotsupport-app"
        for element in artifact["devices"] + artifact["systemSoftware"] + artifact["groupings"]:
            assert "producer" not in element

    def test_elements_have_no_environment_field(
        self, dataset: Any, projection: dict[str, Any], firmware_products: dict[str, str]
    ) -> None:
        """Element kinds reject 'environment' (schema additionalProperties:false)."""
        artifact = genarch.generate_artifact(
            dataset, projection, firmware_products, warn=_silent
        )
        for element in artifact["devices"] + artifact["systemSoftware"] + artifact["groupings"]:
            assert "environment" not in element

    def test_relations_have_valid_ids(
        self, dataset: Any, projection: dict[str, Any], firmware_products: dict[str, str]
    ) -> None:
        """Every relation carries a deterministic, unique 'rel:<uuid>' id."""
        import re

        artifact = genarch.generate_artifact(
            dataset, projection, firmware_products, warn=_silent
        )
        pattern = re.compile(
            r"^rel:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        ids = [r["id"] for r in artifact["relations"]]
        assert all(pattern.match(rid) for rid in ids)
        # Ids are unique (distinct edges never collide).
        assert len(ids) == len(set(ids))

    def test_determinism_byte_identical(
        self, dataset: Any, projection: dict[str, Any], firmware_products: dict[str, str]
    ) -> None:
        a1 = genarch.dump_yaml(
            genarch.generate_artifact(dataset, projection, firmware_products, warn=_silent)
        )
        a2 = genarch.dump_yaml(
            genarch.generate_artifact(dataset, projection, firmware_products, warn=_silent)
        )
        assert a1 == a2

    def test_uuid5_ids_stable_and_namespaced(
        self, dataset: Any, projection: dict[str, Any], firmware_products: dict[str, str]
    ) -> None:
        """device:/ss: ids are uuid5 from the private namespace on Device.key."""
        artifact = genarch.generate_artifact(
            dataset, projection, firmware_products, warn=_silent
        )
        dev_aa = next(
            d for d in artifact["devices"]
            if _hint(d["id"]) == "device:calendar-display-aa11bb22"
        )
        expected = genarch._uuid5("device", "aa11bb22")
        assert dev_aa["id"].endswith(f",{expected}")

    def test_unmapped_model_code_fails(
        self, dataset: Any, projection: dict[str, Any], firmware_products: dict[str, str]
    ) -> None:
        """A device whose model_code is unmapped -> GeneratorError naming the code."""
        # Drop doorbell_receiver from the map; its device must fail the build.
        partial = {k: v for k, v in firmware_products.items() if k != "doorbell_receiver"}
        with pytest.raises(genarch.GeneratorError) as exc:
            genarch.generate_artifact(dataset, projection, partial, warn=_silent)
        assert "doorbell_receiver" in str(exc.value)
