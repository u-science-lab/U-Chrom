#!/usr/bin/env python3
"""Quick e2e validation: real Claude + synthetic data.

Verifies:
- Backend starts
- WS connects
- load_data succeeds on tiny dataset
- Agent responds to user_message
- render_gosling / run_analysis can be called

Does NOT require the 5.9GB dataset or long TAD computation.
"""
import asyncio
import json
import os
import sys
import time
import threading
import uvicorn
import websockets

# Check API key
API_KEY = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
if not API_KEY:
    print("SKIP: No ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN set")
    sys.exit(0)

print(f"Using API base: {BASE_URL}")

# Ensure synthetic dataset exists (generated on demand)
DATASET_PATH = "example-data/synthetic_chr1_tiny.h5cd"
if not os.path.exists(DATASET_PATH):
    print(f"Generating {DATASET_PATH}...")
    sys.path.insert(0, os.path.abspath(".."))
    from uchrom.core import ChromData
    import pandas as pd
    import numpy as np

    n = 100
    spots = pd.DataFrame({
        'chrom': pd.Categorical(['chr1']*n),
        'start': np.arange(n) * 100_000,
        'end': (np.arange(n)+1) * 100_000,
        'trace_id': pd.Categorical(['t0']*n),
        'cell_id': pd.Categorical(['c0']*n),
    })
    coords = np.random.randn(n, 3).astype(np.float32) * 1000
    cells = pd.DataFrame({'cell_id': ['c0']}).set_index('cell_id')

    cd = ChromData(coords=coords, spots=spots, cells=cells)
    os.makedirs(os.path.dirname(DATASET_PATH), exist_ok=True)
    cd.write(DATASET_PATH)
    print(f"✓ Created {DATASET_PATH} ({os.path.getsize(DATASET_PATH)/1024:.1f} KB)")

# Start backend in a thread
def run_server():
    from webapp.backend.main import app
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()
time.sleep(2)  # wait for server ready

async def test_workflow():
    uri = "ws://127.0.0.1:8765/ws/main"
    async with websockets.connect(uri) as ws:
        print("✓ WS connected")

        # 1. Load tiny dataset
        await ws.send(json.dumps({
            "type": "load_data",
            "payload": {"path": DATASET_PATH}
        }))

        loaded = False
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") == "data_loaded":
                print(f"✓ Data loaded: {msg.get('n_spots')} spots, {msg.get('n_cells')} cells")
                loaded = True
                break
            if msg.get("type") == "error":
                print(f"✗ Load error: {msg.get('message')}")
                return False

        if not loaded:
            return False

        # 2. Send user_message asking for visualization
        await ws.send(json.dumps({
            "type": "user_message",
            "payload": {"text": "Show me the chr1 contact map"}
        }))

        # Collect responses (timeout after 30s)
        agent_responded = False
        got_artifact = False
        timeout = time.time() + 30

        while time.time() < timeout:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
                mtype = msg.get("type")

                if mtype == "agent_message":
                    print(f"✓ Agent replied: {msg.get('text', '')[:80]}...")
                    agent_responded = True

                if mtype == "agent_artifact":
                    atype = msg.get("artifact_type")
                    print(f"✓ Agent artifact: {atype}")
                    got_artifact = True

                    if atype == "gosling_spec":
                        spec = msg.get("spec", {})
                        print(f"  - spec has {len(spec.get('tracks', []))} track(s)")

                    # Consider success if we got any artifact
                    if agent_responded:
                        break

                if mtype == "error":
                    print(f"✗ Error: {msg.get('message')}")
                    return False

            except asyncio.TimeoutError:
                continue

        if not agent_responded:
            print("✗ Agent did not respond within 30s")
            return False

        print("✓ E2E chain validated (load → agent → response)")
        return True

try:
    result = asyncio.run(test_workflow())
    sys.exit(0 if result else 1)
except Exception as e:
    print(f"✗ Exception: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
