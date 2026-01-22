#!/bin/sh

docker run \
    -e PGADMIN_DEFAULT_EMAIL=pvginkel@gmail.com \
    -e PGADMIN_DEFAULT_PASSWORD=admin \
    -p 8100:80 \
    -d \
    dpage/pgadmin4:latest

echo "pgAdmin is running on http://localhost:8100"
