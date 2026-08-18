#!/bin/bash
# Minabox Development Tools – run from repo root or via ./scripts/dev-tools.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Farben für Output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

case "$1" in
  check)
    echo -e "${BLUE}🔍 Checking all Python files...${NC}"
    ruff check . --fix
    black . --check
    mypy .
    ;;
  format)
    echo -e "${BLUE}✨ Formatting all Python files...${NC}"
    black .
    ruff check . --fix
    echo -e "${GREEN}✅ Formatting complete!${NC}"
    ;;
  install)
    echo -e "${BLUE}📦 Installing pre-commit hooks...${NC}"
    pre-commit install
    echo -e "${GREEN}✅ Pre-commit hooks installed!${NC}"
    ;;
  test)
    echo -e "${BLUE}🧪 Running pre-commit on all files...${NC}"
    pre-commit run --all-files
    ;;
  pytest)
    echo -e "${BLUE}🧪 Running service test suites...${NC}"
    "$SCRIPT_DIR/run-tests.sh" "${2:-all}"
    ;;
  venv)
    echo -e "${BLUE}🐍 Activating virtual environment...${NC}"
    source .venv/bin/activate
    echo -e "${GREEN}✅ Virtual environment activated!${NC}"
    ;;
  *)
    echo -e "${YELLOW}Minabox Development Tools${NC}"
    echo ""
    echo "Usage: ./scripts/dev-tools.sh [command]"
    echo ""
    echo "Commands:"
    echo "  check    - Check all Python files for issues"
    echo "  format   - Format all Python files"
    echo "  install  - Install pre-commit hooks"
    echo "  test     - Run pre-commit on all files"
    echo "  venv     - Activate virtual environment"
    echo ""
    echo "Git Workflow:"
    echo "  1. Write code"
    echo "  2. git add ."
    echo "  3. git commit -m 'message'  # Pre-commit runs automatically"
    ;;
esac
