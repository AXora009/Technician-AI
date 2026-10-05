#!/bin/bash
# Smoke-tests an extracted package: first-run setup, server start, access control.
#   packaging/smoke_test.sh <package dir> <path to bundled python, relative to it>
set -euo pipefail
cd "$1"
PY="$2"
PORT=8790

"$PY" -c "import technician_ai.api, fitz, numpy, pypdf, docx, openpyxl, pptx, google.genai, uvicorn; print('imports ok')"

# First run: answer the key prompt with a fake key. BROWSER=true makes the browser launch a no-op.
echo "fake-key-for-smoke-test" | PORT=$PORT BROWSER=true "$PY" scripts/local_start.py > server.log 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; cat server.log' EXIT

for _ in $(seq 60); do
  curl -sf "http://127.0.0.1:$PORT/" > /dev/null && break
  sleep 2
done

grep -q "GOOGLE_API_KEY=fake-key-for-smoke-test" .env
CODE=$("$PY" -c "import json; print(next(iter(json.load(open('data/workspaces.json')))))")

status() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
[ "$(status "http://127.0.0.1:$PORT/")" = 200 ]
[ "$(status "http://127.0.0.1:$PORT/api/manuals")" = 401 ]
curl -sf -c cookies.txt -H "Content-Type: application/json" -d "{\"code\":\"$CODE\"}" "http://127.0.0.1:$PORT/api/login" > /dev/null
[ "$(status -b cookies.txt "http://127.0.0.1:$PORT/api/manuals")" = 200 ]
echo "smoke test passed"
