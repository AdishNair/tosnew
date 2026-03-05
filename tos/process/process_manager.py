from __future__ import annotations

import threading
from collections import deque
from typing import Iterable

from process.process import Process, ProcessState


class ProcessManager:
    """Maintains PCB table and queue state transitions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_pid = 1
        self.process_table: dict[int, Process] = {}
        self.ready_queue: deque[int] = deque()
        self.waiting_queue: deque[int] = deque()
        self.running_process: int | None = None

    def create_process(
        self,
        required_seat: str,
        priority: int,
        burst_time: float,
        pages_required: int,
        role: str = "user",
    ) -> Process:
        with self._lock:
            pid = self._next_pid
            self._next_pid += 1
            proc = Process(
                pid=pid,
                priority=priority,
                required_seat=required_seat,
                burst_time=burst_time,
                pages_required=pages_required,
                role=role,
            )
            proc.set_state(ProcessState.READY)
            self.process_table[pid] = proc
            self.ready_queue.append(pid)
            return proc

    def set_running(self, pid: int) -> None:
        with self._lock:
            if pid in self.waiting_queue:
                self.waiting_queue.remove(pid)
            if pid in self.ready_queue:
                self.ready_queue.remove(pid)
            self.running_process = pid
            self.process_table[pid].set_state(ProcessState.RUNNING)

    def set_waiting(self, pid: int) -> None:
        with self._lock:
            if self.running_process == pid:
                self.running_process = None
            if pid not in self.waiting_queue:
                self.waiting_queue.append(pid)
            self.process_table[pid].set_state(ProcessState.WAITING)

    def set_ready(self, pid: int) -> None:
        with self._lock:
            if self.running_process == pid:
                self.running_process = None
            if pid in self.waiting_queue:
                self.waiting_queue.remove(pid)
            if pid not in self.ready_queue:
                self.ready_queue.append(pid)
            self.process_table[pid].set_state(ProcessState.READY)

    def terminate_process(self, pid: int) -> Process | None:
        with self._lock:
            proc = self.process_table.get(pid)
            if not proc:
                return None
            if pid in self.ready_queue:
                self.ready_queue.remove(pid)
            if pid in self.waiting_queue:
                self.waiting_queue.remove(pid)
            if self.running_process == pid:
                self.running_process = None
            proc.set_state(ProcessState.TERMINATED)
            proc.completed = True
            return proc

    def get_process(self, pid: int) -> Process | None:
        with self._lock:
            return self.process_table.get(pid)

    def get_ready_processes(self) -> list[Process]:
        with self._lock:
            return [self.process_table[pid] for pid in self.ready_queue if pid in self.process_table]

    def iter_active(self) -> Iterable[Process]:
        with self._lock:
            return [
                p
                for p in self.process_table.values()
                if p.state not in (ProcessState.TERMINATED,)
            ]

    def count_active(self) -> int:
        with self._lock:
            return sum(1 for p in self.process_table.values() if p.state != ProcessState.TERMINATED)
