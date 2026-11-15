#!/bin/sh
# GigSim and the API in one container. GigSim listens on localhost only, and both processes
# share a random per-boot API token, so nothing outside the container can call GigSim.
set -e
RANDOM_HEX=$(python -c "import secrets; print(secrets.token_hex(16))")
export GIGSIM_API_TOKEN="${GIGSIM_API_TOKEN:-$RANDOM_HEX}"
RANDOM_HEX=$(python -c "import secrets; print(secrets.token_hex(16))")
export GIGSIM_ADMIN_TOKEN="${GIGSIM_ADMIN_TOKEN:-$RANDOM_HEX}"
uvicorn gigsim.app:app --host 127.0.0.1 --port 8081 --log-level warning &
exec uvicorn apps.api.main:app --host 0.0.0.0 --port "${PORT:-7860}"
