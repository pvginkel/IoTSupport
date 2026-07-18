#!/bin/sh
# Build and push the frontend container image with kaniko.
#
# There is no Docker daemon in the environment, so this replaces the old
# docker build chain. Kaniko always pushes — there is no local image store —
# and its sidecar only sees /work, hence the absolute paths.
#
# Usage: scripts/build-image.sh [tag]        (default tag: dev)
#
# Defaults to :dev, never :latest — Jenkins publishes :latest to this same
# registry and the deployment tracks it, so a local build must not clobber it.

set -e

TAG="${1:-dev}"
CONTEXT=/work/IoTSupport/frontend

exec cexec kaniko build.sh \
    --context="$CONTEXT" \
    --dockerfile="$CONTEXT/Dockerfile" \
    --destination="registry:5000/iotsupport-ui:$TAG"
