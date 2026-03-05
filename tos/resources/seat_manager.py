from __future__ import annotations

import threading
import time
from typing import Any

from storage.storage import StorageBackend


class SeatManager:
    """Seat categories are treated as finite shared resources."""

    def __init__(self, storage: StorageBackend) -> None:
        self.storage = storage
        self._lock = threading.Lock()
        self._seats = self.storage.load_seats()
        self._semaphores = {cat: threading.Semaphore(count) for cat, count in self._seats.items()}
        self._allocations: dict[int, str] = {}

    def allocate_seat(self, pid: int, category: str) -> bool:
        with self._lock:
            if pid in self._allocations:
                return True
        if category not in self._semaphores:
            return False
        acquired = self._semaphores[category].acquire(blocking=False)
        if not acquired:
            return False
        with self._lock:
            if self._seats[category] <= 0:
                self._semaphores[category].release()
                return False
            self._seats[category] -= 1
            self._allocations[pid] = category
            self.storage.save_seats(self._seats)
            self.storage.append_booking(
                {
                    "process_id": pid,
                    "seat_category": category,
                    "timestamp": time.time(),
                }
            )
            return True

    def release_seat(self, pid: int) -> bool:
        with self._lock:
            category = self._allocations.pop(pid, None)
            if category is None:
                return False
            self._seats[category] += 1
            self.storage.save_seats(self._seats)
            self._semaphores[category].release()
            return True

    def available(self) -> dict[str, int]:
        with self._lock:
            return dict(self._seats)

    def is_exhausted(self) -> bool:
        with self._lock:
            return all(count <= 0 for count in self._seats.values())

    def get_allocation(self, pid: int) -> str | None:
        with self._lock:
            return self._allocations.get(pid)

    def snapshot_for_banker(self) -> tuple[list[str], list[int], dict[int, dict[str, int]], dict[int, dict[str, int]]]:
        with self._lock:
            categories = list(self._seats.keys())
            available = [self._seats[c] for c in categories]
            allocation: dict[int, dict[str, int]] = {}
            max_need: dict[int, dict[str, int]] = {}
            for pid, seat in self._allocations.items():
                allocation[pid] = {c: 1 if c == seat else 0 for c in categories}
                max_need[pid] = {c: 1 if c == seat else 0 for c in categories}
            return categories, available, allocation, max_need

    def force_release(self, pid: int) -> dict[str, Any]:
        released = self.release_seat(pid)
        return {"pid": pid, "released": released}

    def consume_allocation(self, pid: int) -> bool:
        with self._lock:
            if pid not in self._allocations:
                return False
            self._allocations.pop(pid, None)
            return True
