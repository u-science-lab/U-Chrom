#!/bin/bash
# Automated tests that don't require manual interaction
# Run from worktree root: ./scripts/auto_test.sh

set -e

echo "🤖 U-Chrom Automated Tests"
echo "============================"
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASS++))
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAIL++))
    fi
}

# Test 1: TypeScript compilation
echo "📝 Test 1: TypeScript compilation"
cd webapp/frontend
if npx tsc --noEmit > /dev/null 2>&1; then
    test_result 0
else
    test_result 1
    npx tsc --noEmit 2>&1 | tail -5
fi
cd ../..

# Test 2: Tileset API tests
echo "🗺️  Test 2: Tileset API tests (14 tests)"
if .venv/bin/python -m pytest tests/test_tileset_api.py tests/integration/test_gosling_compat.py -q > /dev/null 2>&1; then
    test_result 0
else
    test_result 1
    .venv/bin/python -m pytest tests/test_tileset_api.py tests/integration/test_gosling_compat.py -v 2>&1 | tail -10
fi

# Test 3: Data API tests
echo "📊 Test 3: Data API tests"
if .venv/bin/python -m pytest tests/test_data_api.py -q > /dev/null 2>&1; then
    test_result 0
else
    test_result 1
fi

# Test 4: Structure API tests
echo "🧬 Test 4: Structure API tests (TAD/loop)"
if .venv/bin/python -m pytest tests/test_strc_api.py -q > /dev/null 2>&1; then
    test_result 0
else
    test_result 1
fi

# Test 5: Integration data flow
echo "🔄 Test 5: Integration data flow"
if .venv/bin/python -m pytest tests/integration/test_data_flow.py -q > /dev/null 2>&1; then
    test_result 0
else
    test_result 1
fi

# Test 6: Test collection (no stale imports)
echo "📦 Test 6: Test collection (no import errors)"
if .venv/bin/python -m pytest tests/ --collect-only -q > /dev/null 2>&1; then
    test_result 0
else
    test_result 1
    .venv/bin/python -m pytest tests/ --collect-only -q 2>&1 | grep -i error | head -5
fi

# Test 7: Check example data exists
echo "📁 Test 7: Example data availability"
if [ -f "/Users/bakezq/Coding/U-Chrom/example-data/test_20cells_chr21.h5cd" ]; then
    test_result 0
else
    echo -e "${YELLOW}⚠ SKIP (data not found)${NC}"
    ((SKIP++))
fi

# Test 8: Frontend dependencies
echo "📦 Test 8: Frontend dependencies installed"
if [ -d "webapp/frontend/node_modules" ]; then
    test_result 0
else
    test_result 1
fi

# Test 9: Backend can import (quick smoke)
echo "🐍 Test 9: Backend imports check"
if .venv/bin/python -c "from webapp.backend.main import app; from webapp.backend.agent_tools import TOOLS; print('OK')" > /dev/null 2>&1; then
    test_result 0
else
    test_result 1
fi

# Summary
echo ""
echo "============================"
echo "📊 Test Summary"
echo "============================"
echo -e "${GREEN}PASS: $PASS${NC}"
echo -e "${RED}FAIL: $FAIL${NC}"
echo -e "${YELLOW}SKIP: $SKIP${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    echo ""
    echo "Ready for manual E2E testing:"
    echo "1. Start backend: .venv/bin/uvicorn webapp.backend.main:app --reload --port 8000"
    echo "2. Start frontend: cd webapp/frontend && npm run dev"
    echo "3. Open browser: http://localhost:5173"
    echo "4. Follow manual test checklist in context/20260611-frontend-completeness-and-e2e-plan.md"
    exit 0
else
    echo -e "${RED}❌ $FAIL test(s) failed${NC}"
    exit 1
fi
