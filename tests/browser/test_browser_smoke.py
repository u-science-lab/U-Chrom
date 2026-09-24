"""Smoke test for the PyVista + PyQt5 browser.

Runs in a subprocess: VTK/Qt failures are often hard crashes (segfaults)
that would otherwise take down the whole pytest session.  Needs a GL
display — native on macOS/Windows, ``xvfb-run`` on Linux CI.
"""
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyvista")
pytest.importorskip("pyvistaqt")
pytest.importorskip("qdarkgraystyle")

pytestmark = pytest.mark.browser

SCRIPT = textwrap.dedent("""
    import numpy as np, pandas as pd
    from uchrom.browser.utils import get_qapp
    from uchrom.browser.main_window import MainWindow

    app = get_qapp()
    n = 20
    t = np.linspace(0, 2 * np.pi, n)
    df = pd.DataFrame({"chrom": ["chr1"] * 10 + ["chr2"] * 10,
                       "start": np.arange(n) * 1000})
    df["end"] = df["start"] + 1000
    df["x"], df["y"], df["z"] = np.cos(t), np.sin(t), t

    win = MainWindow()
    win.load_model(df, "toy.csv")
    win.init_draw()
    assert len(win.canvas.control_panel.layers) == 1
    assert set(win.chr_colormap) == {"chr1", "chr2"}
    win.add_canvas("h")
    assert len(list(win.get_all_canvas())) == 2
    win.close()
    print("BROWSER_OK")
""")


def test_main_window_loads_and_draws(tmp_path):
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        pytest.skip("no X display (run under xvfb-run)")
    env = {k: v for k, v in os.environ.items() if k != "PYVISTA_OFF_SCREEN"}
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0 and "BROWSER_OK" in proc.stdout, (
        f"rc={proc.returncode}\nstdout:\n{proc.stdout[-2000:]}\n"
        f"stderr:\n{proc.stderr[-4000:]}"
    )
