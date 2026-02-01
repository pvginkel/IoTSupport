#!/bin/sh

CONTAINER_NAME="pgadmin"

# Stop and remove existing container if running
docker stop "$CONTAINER_NAME" 2>/dev/null
docker rm "$CONTAINER_NAME" 2>/dev/null

mkdir -p ~/.pgadmin
sudo chown -R 5050:5050 ~/.pgadmin

docker run \
    --name "$CONTAINER_NAME" \
    -e PGADMIN_DEFAULT_EMAIL=pvginkel@gmail.com \
    -e PGADMIN_DEFAULT_PASSWORD=admin \
    -v ~/.pgadmin:/var/lib/pgadmin \
    -p 8100:80 \
    -d \
    dpage/pgadmin4:latest

echo "pgAdmin is running on http://localhost:8100"
