from __future__ import annotations

from collections import defaultdict

from process.process import Process


class Scheduler:
    """Supports FCFS, SJF, Round Robin, and Priority scheduling."""

    def __init__(self, algorithm: str = "FCFS", time_quantum: float = 0.03) -> None:
        self.algorithm = algorithm.upper()
        self.time_quantum = time_quantum
        self._rr_last_index = defaultdict(int)

    def set_algorithm(self, algorithm: str) -> None:
        self.algorithm = algorithm.upper()

    def pick_next(self, ready_processes: list[Process]) -> Process | None:
        if not ready_processes:
            return None

        algo = self.algorithm
        if algo == "FCFS":
            return min(ready_processes, key=lambda p: p.pcb.arrival_time)
        if algo == "SJF":
            return min(ready_processes, key=lambda p: (p.pcb.burst_time, p.pcb.arrival_time))
        if algo == "PRIORITY":
            return max(ready_processes, key=lambda p: (p.priority, -p.pcb.arrival_time))
        if algo == "ROUND_ROBIN":
            ordered = sorted(ready_processes, key=lambda p: p.pcb.arrival_time)
            key = len(ordered)
            idx = self._rr_last_index[key] % key
            self._rr_last_index[key] += 1
            return ordered[idx]
        raise ValueError(f"Unsupported scheduler algorithm: {self.algorithm}")
