mkdir -p $(pwd)/tmp

NAME=electronics-inventory
ARGS="
    -p 3201:3201
    -v $(pwd)/tmp:/data
    -e ESP32_CONFIGS_DIR=/data/esp32-configs
    -e ASSETS_DIR=/data/assets
    -e SIGNING_KEY_PATH=/data/signing_key.pem
"
