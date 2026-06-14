"""Jupyter kernel management and code execution API."""
from typing import Optional
import jupyter_client
import logging
import threading
import time

logger = logging.getLogger(__name__)

# Global kernel manager and client
_kernel_manager: Optional[jupyter_client.KernelManager] = None
_kernel_client: Optional[jupyter_client.KernelClient] = None
_kernel_lock = threading.Lock()

# Tracks which h5cd path the live kernel was last seeded with, so re-seeding the
# same dataset is a no-op (re-seeding a *different* dataset re-binds ``cd``).
_seeded_path: Optional[str] = None


def start_kernel():
    """Start a new Jupyter kernel."""
    global _kernel_manager, _kernel_client

    with _kernel_lock:
        if _kernel_manager is not None:
            logger.info("Kernel already running")
            return

        _kernel_manager = jupyter_client.KernelManager()
        _kernel_manager.start_kernel()
        _kernel_client = _kernel_manager.client()
        _kernel_client.start_channels()

        # Wait for kernel to be ready
        try:
            _kernel_client.wait_for_ready(timeout=10)
        except RuntimeError:
            logger.warning("Kernel may not be fully ready")

        logger.info("Kernel started")


def seed_kernel(h5cd_path: str, force: bool = False) -> None:
    """Inject ``cd`` (the loaded ChromData) into the kernel namespace.

    The notebook cells the agent and user run reference ``cd`` directly, so the
    kernel must have it bound before any analysis code executes. This also
    activates ipykernel's ``%matplotlib inline`` backend so figures are flushed
    as ``display_data`` messages carrying ``image/png`` (the standard Jupyter
    inline-figure path) instead of trying to open a GUI window in the headless
    kernel process. A plain ``Agg`` backend renders to a buffer but never emits
    a display message, so the image would never reach the frontend.

    Idempotent per dataset: re-seeding the same path is skipped; seeding a new
    path re-binds ``cd`` without restarting the kernel.

    Args:
        h5cd_path: Absolute path to the .h5cd file to load.
        force: Re-run the init code even if this path was already seeded.
    """
    global _seeded_path

    with _kernel_lock:
        if _kernel_client is None:
            raise RuntimeError("Kernel not started. Call start_kernel() first.")

        if not force and _seeded_path == h5cd_path:
            logger.info("Kernel already seeded with %s; skipping", h5cd_path)
            return

        # repr() produces a safely-quoted Python string literal, so paths with
        # spaces, quotes or backslashes can't break out of the code string.
        init_code = (
            "%matplotlib inline\n"
            "import matplotlib\n"
            "import numpy as np\n"
            "import pandas as pd\n"
            "from uchrom.core import ChromData\n"
            f"cd = ChromData.read({h5cd_path!r})\n"
        )
        # Fire the init code on the shell channel. We don't need to collect the
        # echo, but recording the path lets us skip redundant re-seeds.
        _kernel_client.execute(init_code)
        _seeded_path = h5cd_path
        logger.info("Kernel seeded with %s", h5cd_path)


def execute_code(code: str, timeout: float = 30.0) -> dict:
    """Execute code in the kernel and return results.

    Args:
        code: Python code to execute
        timeout: Maximum execution time in seconds (default 30s)

    Returns:
        dict with keys: status, output, error, images. ``images`` is a list of
        base64-encoded PNG strings (one per matplotlib figure / rich display).
    """
    with _kernel_lock:
        if _kernel_client is None:
            raise RuntimeError("Kernel not started. Call start_kernel() first.")

        # Execute code
        msg_id = _kernel_client.execute(code)
        start_time = time.time()

        # Collect outputs
        outputs = []
        errors = []
        images = []

        # Wait for execution to complete by checking the shell channel
        idle_reached = False

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return {
                    "status": "error",
                    "output": '\n'.join(outputs),
                    "error": f"Execution timeout after {timeout}s",
                    "images": images,
                }

            try:
                remaining = timeout - elapsed
                msg = _kernel_client.get_iopub_msg(timeout=min(remaining, 1.0))
                msg_type = msg['header']['msg_type']

                if msg_type == 'execute_result':
                    data = msg['content'].get('data', {})
                    # Some rich reprs emit the figure here rather than as a
                    # separate display_data message.
                    if 'image/png' in data:
                        images.append(data['image/png'])
                    elif 'text/plain' in data:
                        outputs.append(data['text/plain'])
                elif msg_type == 'display_data':
                    # The inline matplotlib backend flushes figures here.
                    data = msg['content'].get('data', {})
                    if 'image/png' in data:
                        images.append(data['image/png'])
                    elif 'text/plain' in data:
                        outputs.append(data['text/plain'])
                elif msg_type == 'stream':
                    outputs.append(msg['content']['text'])
                elif msg_type == 'error':
                    errors.append('\n'.join(msg['content']['traceback']))
                elif msg_type == 'status' and msg['content']['execution_state'] == 'idle':
                    idle_reached = True
                    # Continue reading to catch any remaining messages
            except Exception as e:
                # Timeout or queue empty - if we've reached idle, we're done
                if idle_reached:
                    break
                logger.debug(f"Timeout waiting for message: {e}")
                # If we haven't reached idle yet, keep waiting
                continue

        return {
            "status": "error" if errors else "ok",
            "output": '\n'.join(outputs),
            "error": '\n'.join(errors) if errors else None,
            "images": images,
        }


def stop_kernel():
    """Stop the running kernel."""
    global _kernel_manager, _kernel_client, _seeded_path

    with _kernel_lock:
        if _kernel_client:
            _kernel_client.stop_channels()
            _kernel_client = None

        if _kernel_manager:
            _kernel_manager.shutdown_kernel(now=True)
            _kernel_manager = None
            logger.info("Kernel stopped")

        # Namespace is gone with the kernel; force a re-seed on next load.
        _seeded_path = None
