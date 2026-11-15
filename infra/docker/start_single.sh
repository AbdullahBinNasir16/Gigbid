#!/bin/sh
# GigSim and the API in one container. GigSim listens on localhost only.
set -e
uvicorn gigsim.app:app --host 127.0.0.1 --port 8081 --log-level warning &
exec uvicorn apps.api.main:app --host 0.0.0.0 --port "${PORT:-7860}"
