#!/bin/sh
set -eu

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=langfuse_db="$LANGFUSE_DB" \
  --command 'CREATE DATABASE :"langfuse_db"'
