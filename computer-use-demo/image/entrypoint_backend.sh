#!/bin/bash
set -e

./start_all.sh
./novnc_startup.sh

python http_server.py > /tmp/server_logs.txt 2>&1 &

echo "Starting FastAPI backend on :8080"
python -m backend.main


