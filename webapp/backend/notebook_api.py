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


def execute_code(code: str, timeout: float = 30.0) -> dict:
    """Execute code in the kernel and return results.

    Args:
        code: Python code to execute
        timeout: Maximum execution time in seconds (default 30s)

    Returns:
        dict with keys: status, output, error
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

        # Wait for execution to complete by checking the shell channel
        idle_reached = False

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return {
                    "status": "error",
                    "output": '\n'.join(outputs),
                    "error": f"Execution timeout after {timeout}s"
                }

            try:
                remaining = timeout - elapsed
                msg = _kernel_client.get_iopub_msg(timeout=min(remaining, 1.0))
                msg_type = msg['header']['msg_type']

                if msg_type == 'execute_result':
                    outputs.append(msg['content']['data'].get('text/plain', ''))
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
            "error": '\n'.join(errors) if errors else None
        }


def stop_kernel():
    """Stop the running kernel."""
    global _kernel_manager, _kernel_client

    with _kernel_lock:
        if _kernel_client:
            _kernel_client.stop_channels()
            _kernel_client = None

        if _kernel_manager:
            _kernel_manager.shutdown_kernel(now=True)
            _kernel_manager = None
            logger.info("Kernel stopped")
