from __future__ import annotations

import random
import threading
from collections import deque


class MemoryManager:
    """Simulates fixed partitioning + paging with replacement policies."""

    def __init__(self, total_frames: int = 64, partition_sizes: list[int] | None = None) -> None:
        self.total_frames = total_frames
        self.free_frames = total_frames
        self.partition_sizes = partition_sizes or [4, 8, 16, 32]
        self.partition_usage: dict[int, int] = {}
        self.page_table: dict[int, list[int]] = {}
        self.frame_owner: dict[int, int] = {}
        self.frame_queue_fifo: deque[int] = deque()
        self.frame_last_used: dict[int, int] = {}
        self._tick = 0
        self._lock = threading.Lock()

    def allocate(self, pid: int, pages_required: int, replacement_algo: str = "FIFO") -> bool:
        with self._lock:
            partition = self._pick_partition(pages_required)
            if partition is None:
                return False
            self.partition_usage[pid] = partition
            needed = pages_required
            if self.free_frames < needed:
                self._replace_pages(needed - self.free_frames, replacement_algo)
            if self.free_frames < needed:
                return False

            allocated_frames = []
            next_frame = 0
            while len(allocated_frames) < needed:
                if next_frame not in self.frame_owner:
                    self.frame_owner[next_frame] = pid
                    self.frame_queue_fifo.append(next_frame)
                    self.frame_last_used[next_frame] = self._tick
                    self._tick += 1
                    allocated_frames.append(next_frame)
                next_frame += 1

            self.page_table[pid] = allocated_frames
            self.free_frames -= len(allocated_frames)
            return True

    def access_page(self, pid: int, page_index: int) -> bool:
        with self._lock:
            pages = self.page_table.get(pid, [])
            if not pages or page_index >= len(pages):
                return False
            frame = pages[page_index]
            self.frame_last_used[frame] = self._tick
            self._tick += 1
            return True

    def release(self, pid: int) -> None:
        with self._lock:
            frames = self.page_table.pop(pid, [])
            for frame in frames:
                self.frame_owner.pop(frame, None)
                self.frame_last_used.pop(frame, None)
                try:
                    self.frame_queue_fifo.remove(frame)
                except ValueError:
                    pass
            self.free_frames += len(frames)
            self.partition_usage.pop(pid, None)

    def simulate_thrashing(self, pids: list[int], rounds: int = 200) -> dict[str, int]:
        with self._lock:
            page_faults = 0
            accesses = 0
            for _ in range(rounds):
                pid = random.choice(pids)
                pages = self.page_table.get(pid, [])
                accesses += 1
                if not pages:
                    page_faults += 1
                    continue
                page_idx = random.randint(0, len(pages) + 1)
                if page_idx >= len(pages):
                    page_faults += 1
                else:
                    frame = pages[page_idx]
                    self.frame_last_used[frame] = self._tick
                    self._tick += 1
            return {"accesses": accesses, "page_faults": page_faults}

    def _pick_partition(self, pages_required: int) -> int | None:
        for size in sorted(self.partition_sizes):
            if pages_required <= size:
                return size
        return None

    def _replace_pages(self, needed: int, algo: str) -> None:
        victims: list[int] = []
        policy = algo.upper()
        if policy == "FIFO":
            while len(victims) < needed and self.frame_queue_fifo:
                victims.append(self.frame_queue_fifo.popleft())
        elif policy == "LRU":
            by_age = sorted(self.frame_last_used.items(), key=lambda item: item[1])
            victims = [frame for frame, _ in by_age[:needed]]
        elif policy == "OPTIMAL":
            # Approximation: evict frames with largest frame index to emulate future-distance heuristic.
            victims = sorted(self.frame_owner.keys(), reverse=True)[:needed]
        else:
            raise ValueError(f"Unsupported page replacement policy: {algo}")

        for frame in victims:
            owner = self.frame_owner.pop(frame, None)
            if owner is None:
                continue
            if owner in self.page_table and frame in self.page_table[owner]:
                self.page_table[owner].remove(frame)
            self.frame_last_used.pop(frame, None)
            try:
                self.frame_queue_fifo.remove(frame)
            except ValueError:
                pass
            self.free_frames += 1
