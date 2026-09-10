#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
curl --fail --silent --show-error --retry 5 --retry-connrefused "${BASE_URL}/api/v1/health" >/dev/null
curl --fail --silent --show-error "${BASE_URL}/openapi.json" >/dev/null
curl --fail --silent --show-error "${BASE_URL}/" >/dev/null
curl --fail --silent --show-error "${BASE_URL}/app.js" >/dev/null
echo "smoke test passed: ${BASE_URL}"
