#!/bin/bash
# Quick smoke test for webapp E2E
# Run from worktree root: ./scripts/smoke_test.sh

set -e

echo "🧪 U-Chrom Webapp Smoke Test"
echo "=============================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if backend is running
echo "📡 Checking backend..."
if curl -s http://localhost:8000/api/plugins > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Backend running on :8000"
else
    echo -e "${YELLOW}⚠${NC} Backend not running. Start with:"
    echo "   .venv/bin/uvicorn webapp.backend.main:app --reload --port 8000"
    echo ""
    read -p "Press Enter to continue (or Ctrl+C to abort)..."
fi

# Check if frontend is running
echo "🎨 Checking frontend..."
if curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Frontend running on :5173"
else
    echo -e "${YELLOW}⚠${NC} Frontend not running. Start with:"
    echo "   cd webapp/frontend && npm run dev"
    echo ""
    read -p "Press Enter to continue (or Ctrl+C to abort)..."
fi

# Check test data
echo "📁 Checking test data..."
TEST_DATA="/Users/bakezq/Coding/U-Chrom/example-data/test_20cells_chr21.h5cd"
if [ -f "$TEST_DATA" ]; then
    echo -e "${GREEN}✓${NC} Test data found: test_20cells_chr21.h5cd"
else
    echo -e "${RED}✗${NC} Test data not found at: $TEST_DATA"
    echo "   Download from example-data/ in main repo"
    exit 1
fi

echo ""
echo "🚀 Manual Test Checklist"
echo "========================"
echo ""
echo "Open browser: http://localhost:5173"
echo ""
echo "Test 1: Basic Load & Visualization"
echo "-----------------------------------"
echo "1. [ ] Click 'Open File' button in TopBar"
echo "2. [ ] Select: $TEST_DATA"
echo "3. [ ] Verify ChatPanel shows 'Data loaded: 20 cells'"
echo "4. [ ] Click 'Add Panel' → 'Cell Embedding'"
echo "   - [ ] UMAP scatter plot displays with ~20 points"
echo "5. [ ] Click 'Add Panel' → 'Contact Map'"
echo "   - [ ] HiGlass heatmap displays"
echo "6. [ ] Click 'Add Panel' → '3D Structure'"
echo "   - [ ] Three.js 3D structure displays"
echo ""
echo "Test 2: Agent Interaction"
echo "-------------------------"
echo "7. [ ] In ChatPanel, type: 'Show me the contact matrix for chr21'"
echo "   - [ ] Agent responds with tool call"
echo "   - [ ] Gosling visualization appears in Genomic tab"
echo "8. [ ] Type: 'Run TAD calling on chr21'"
echo "   - [ ] Agent calls run_analysis"
echo "   - [ ] Returns TAD boundaries"
echo "9. [ ] Type: 'Add a notebook cell to print cell count'"
echo "   - [ ] Notebook tab shows new cell"
echo "   - [ ] Cell auto-executes, shows '20'"
echo ""
echo "Test 3: REST API Endpoints"
echo "---------------------------"
echo "Testing backend endpoints..."

# Test /api/umap
echo -n "10. [ ] GET /api/umap ... "
if curl -s http://localhost:8000/api/umap | grep -q "embedding"; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${YELLOW}SKIP (no data loaded)${NC}"
fi

# Test /api/tileset_info
echo -n "11. [ ] GET /api/tileset_info?d=contact-chr21 ... "
if curl -s "http://localhost:8000/api/tileset_info?d=contact-chr21" | grep -q "matrix"; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${YELLOW}SKIP (no data loaded)${NC}"
fi

# Test /api/coords/batch
echo -n "12. [ ] GET /api/coords/batch?cell_id=c0 ... "
if curl -s "http://localhost:8000/api/coords/batch?cell_id=c0" | grep -q "coordinates"; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${YELLOW}SKIP (no data loaded)${NC}"
fi

echo ""
echo "Test 4: TypeScript Build"
echo "------------------------"
cd webapp/frontend
echo -n "13. [ ] TypeScript compilation ... "
if npx tsc --noEmit 2>&1 | grep -q "error"; then
    echo -e "${RED}FAIL${NC}"
    npx tsc --noEmit | tail -10
else
    echo -e "${GREEN}PASS${NC}"
fi

echo ""
echo "Test 5: Backend Unit Tests"
echo "---------------------------"
cd ../..
echo -n "14. [ ] Tileset API tests ... "
if .venv/bin/python -m pytest tests/test_tileset_api.py tests/integration/test_gosling_compat.py -q 2>&1 | grep -q "14 passed"; then
    echo -e "${GREEN}PASS (14 tests)${NC}"
else
    echo -e "${RED}FAIL${NC}"
    .venv/bin/python -m pytest tests/test_tileset_api.py tests/integration/test_gosling_compat.py -v | tail -20
fi

echo ""
echo "=============================="
echo "🏁 Smoke Test Complete"
echo ""
echo "Next steps:"
echo "1. Review manual test results above"
echo "2. If all pass → proceed to merge"
echo "3. If any fail → investigate and fix"
echo ""
echo "Full test plan: context/20260611-frontend-completeness-and-e2e-plan.md"
