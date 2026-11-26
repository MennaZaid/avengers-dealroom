#!/usr/bin/env bash
# Waits until the local search engine returns results again (checks every 10 min, up to 8 h), then re-runs research slowly.
cd "$(dirname "$0")"
for i in $(seq 1 48); do
  n=$(curl -s "http://localhost:8080/search?q=Egypt+fintech&format=json" | ../hackathon/.venv/Scripts/python -c "import sys,json;print(len(json.load(sys.stdin)['results']))" 2>/dev/null || echo 0)
  echo "$(date +%H:%M) check $i: $n results"
  if [ "${n:-0}" -gt 0 ]; then
    SEARXNG_MIN_INTERVAL=8 PYTHONIOENCODING=utf-8 ../hackathon/.venv/Scripts/python -m dealroom.research
    exit 0
  fi
  sleep 600
done
echo "search still blocked after 8 hours; research left unchanged"
