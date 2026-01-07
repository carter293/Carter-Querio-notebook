"""Kernel manager for process lifecycle and IPC."""
import asyncio
from multiprocessing import Process, Queue
from typing import Optional
from .types import ExecuteRequest, ExecutionResult
from .process import kernel_main


class KernelManager:
    """Manages kernel process lifecycle and IPC."""

    def __init__(self):
        self.input_queue: Optional[Queue] = None
        self.output_queue: Optional[Queue] = None
        self.process: Optional[Process] = None
        self._running = False

    def start(self):
        """Start the kernel process."""
        if self._running:
            return

        self.input_queue = Queue()
        self.output_queue = Queue()
        self.process = Process(
            target=kernel_main,
            args=(self.input_queue, self.output_queue)
        )
        self.process.start()
        self._running = True
        print(f"[KernelManager] Started kernel process (PID: {self.process.pid})")

    def stop(self):
        """Stop the kernel process."""
        if not self._running:
            return

        # Send shutdown signal
        self.input_queue.put({'type': 'shutdown'})
        self.process.join(timeout=5)

        if self.process.is_alive():
            self.process.terminate()

        self._running = False
        print("[KernelManager] Stopped kernel process")

    async def execute(self, request: ExecuteRequest) -> ExecutionResult:
        """
        Send execution request to kernel and wait for result.

        Returns:
            ExecutionResult with outputs, errors, and metadata
        """
        if not self._running:
            raise RuntimeError("Kernel not running")

        # Send request
        self.input_queue.put(request.model_dump())

        # Wait for result (with timeout)
        loop = asyncio.get_event_loop()
        result_data = await loop.run_in_executor(None, self.output_queue.get)

        return ExecutionResult(**result_data)

    def restart(self):
        """Restart the kernel process."""
        print("[KernelManager] Restarting kernel")
        self.stop()
        self.start()
