#!/bin/sh
# Build and push the backend container image with kaniko.
#
# There is no Docker daemon in the environment. `kaniko` is a dev-container
# binary (not a cexec target): it tars the context where it stands and streams
# it to the builder sidecar, which mounts nothing else — so every path the
# Dockerfile reads must live under --context, and backend/.dockerignore is what
# keeps the transfer small. Kaniko always pushes; there is no local image store.
#
# Usage: scripts/build-image.sh [tag]        (default tag: dev)
#
# Defaults to :dev, never :latest — Jenkins publishes :latest and :<build> to
# this same registry and the deployment tracks them, so a local build must not
# be able to clobber them.

set -e

TAG="${1:-dev}"

exec kaniko \
    --context=/work/IoTSupport/backend \
    --destination="registry:5000/iotsupport-app:$TAG"
