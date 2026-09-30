"""Add the peak GPU memory of an nvidia-smi sample file (MiB per line) to a run.py summary JSON.

    python gpumem.py RUN.gpumem RUN.json
"""

import json
import sys
from pathlib import Path


def main() -> None:
    samples, js = Path(sys.argv[1]), Path(sys.argv[2])
    if not js.exists():
        return
    vals = []
    if samples.exists():
        for line in samples.read_text().split():
            try:
                vals.append(float(line))
            except ValueError:
                pass
    s = json.loads(js.read_text())
    s["gpu_mem_gb"] = max(vals) / 1024 if vals else None
    s["gpu_mem_samples"] = len(vals)
    js.write_text(json.dumps(s, indent=1))
    print(f"peak GPU memory {s['gpu_mem_gb']} GB over {len(vals)} samples")


if __name__ == "__main__":
    main()
