#!/usr/bin/env bash

# Match Docker: access log off unless UVICORN_ACCESS_LOG=true
if [ "${UVICORN_ACCESS_LOG:-}" = "true" ] || [ "${UVICORN_ACCESS_LOG:-}" = "1" ]; then
  exec uvicorn main:app --host 127.0.0.1 --port 8001 --reload
else
  exec uvicorn main:app --host 127.0.0.1 --port 8001 --reload --no-access-log
fi
