from __future__ import annotations

import queue
import threading
import time
from typing import Any

from storage.storage import StorageBackend


class Logger:
    """Asynchronous logger using a producer-consumer queue."""

    def __init__(self, storage: StorageBackend) -> None:
        self.storage = storage
        self.log_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._consume, daemon=True, name="tos-log-consumer")
        self._thread.start()

    def log(self, event: str, pid: int | None = None, details: dict[str, Any] | None = None) -> None:
        self.log_queue.put(
            {
                "timestamp": time.time(),
                "event": event,
                "process_id": pid,
                "details": details or {},
            }
        )

    def _consume(self) -> None:
        while not self._stop_event.is_set() or not self.log_queue.empty():
            try:
                entry = self.log_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            self.storage.append_log(entry)
            self.log_queue.task_done()

    def shutdown(self) -> None:
        self._stop_event.set()
        self.log_queue.join()
        self._thread.join(timeout=2)
