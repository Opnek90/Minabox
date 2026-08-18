#!/bin/bash
# Run the service test suites.
#
# The service dependencies live in the Docker images, not in the repo .venv, so
# the tests run inside the images they belong to. Each suite gets its own
# service source mounted read-only.
#
# Usage: ./scripts/run-tests.sh [backend|audio]

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
PYTEST_PKGS="pytest 'pytest-asyncio<1.2'"
FAILED=0

run_suite() {
  local name="$1" image="$2" src="$3" tests="$4"
  if [ ! -d "$tests" ]; then
    echo -e "${BLUE}– $name: keine Tests${NC}"
    return 0
  fi
  echo -e "${BLUE}▶ $name${NC}"
  docker run --rm \
    -v "$REPO_ROOT/$src:/w/src:ro" \
    -v "$REPO_ROOT/$tests:/w/tests:ro" \
    -w /w \
    -e PYTHONPATH=/w/src \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e DATA_PATH=/tmp \
    -e STATIC_DIR=/tmp/static \
    --entrypoint sh "$image" -c \
    "pip install --quiet --disable-pip-version-check $PYTEST_PKGS >/dev/null 2>&1;
     python -m pytest tests -q -p no:cacheprovider --asyncio-mode=strict --disable-warnings"
  local rc=$?
  [ $rc -ne 0 ] && FAILED=1
  return $rc
}

case "${1:-all}" in
  backend) run_suite "backend-service" minabox-backend \
             services/backend-service/src services/backend-service/tests ;;
  audio)   run_suite "audio-service" minabox-audio \
             services/audio-service/src services/audio-service/tests ;;
  display) run_suite "display-service" minabox-display \
             services/display-service/src services/display-service/tests ;;
  all)
    run_suite "backend-service" minabox-backend \
      services/backend-service/src services/backend-service/tests
    echo
    run_suite "audio-service" minabox-audio \
      services/audio-service/src services/audio-service/tests
    echo
    run_suite "display-service" minabox-display \
      services/display-service/src services/display-service/tests
    ;;
  *) echo "Usage: $0 [all|backend|audio]"; exit 2 ;;
esac

echo
if [ $FAILED -eq 0 ]; then
  echo -e "${GREEN}✅ Alle Tests bestanden${NC}"
else
  echo -e "${RED}❌ Tests fehlgeschlagen${NC}"
fi
exit $FAILED
