from __future__ import annotations

import threading
from collections import defaultdict

from process.process import Process
from process.process import ProcessState


class DeadlockManager:
    """RAG + cycle detection + Banker's safety check."""

    def __init__(self) -> None:
        self._graph: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.Lock()

    def add_request(self, pid: int, resource: str) -> None:
        with self._lock:
            self._graph[f"P{pid}"].add(f"R{resource}")

    def grant(self, pid: int, resource: str) -> None:
        with self._lock:
            proc = f"P{pid}"
            res = f"R{resource}"
            self._graph[proc].discard(res)
            self._graph[res].add(proc)

    def release(self, pid: int, resource: str) -> None:
        with self._lock:
            self._graph[f"R{resource}"].discard(f"P{pid}")
            self._graph[f"P{pid}"].discard(f"R{resource}")

    def detect_deadlock(self) -> tuple[bool, list[str]]:
        with self._lock:
            visited: set[str] = set()
            stack: set[str] = set()
            path: list[str] = []

            def dfs(node: str) -> bool:
                visited.add(node)
                stack.add(node)
                path.append(node)
                for neighbor in self._graph.get(node, set()):
                    if neighbor not in visited:
                        if dfs(neighbor):
                            return True
                    elif neighbor in stack:
                        path.append(neighbor)
                        return True
                stack.remove(node)
                path.pop()
                return False

            for node in list(self._graph.keys()):
                if node not in visited and dfs(node):
                    return True, path[:]
            return False, []

    def bankers_safe_state(
        self,
        categories: list[str],
        available: list[int],
        allocation: dict[int, dict[str, int]],
        max_need: dict[int, dict[str, int]],
    ) -> bool:
        work = available[:]
        finish = {pid: False for pid in max_need}

        while True:
            progress = False
            for pid in max_need:
                if finish[pid]:
                    continue
                need = [max_need[pid][c] - allocation.get(pid, {}).get(c, 0) for c in categories]
                if all(need[i] <= work[i] for i in range(len(categories))):
                    alloc = [allocation.get(pid, {}).get(c, 0) for c in categories]
                    work = [work[i] + alloc[i] for i in range(len(categories))]
                    finish[pid] = True
                    progress = True
            if not progress:
                break
        return all(finish.values())

    def resolve_by_terminating_lowest_priority(self, processes: list[Process]) -> int | None:
        active = [p for p in processes if p.state != ProcessState.TERMINATED]
        if not active:
            return None
        victim = min(active, key=lambda p: p.priority)
        return victim.pid

    def generate_synthetic_deadlock(self, pids: list[int], resources: list[str]) -> None:
        # Create a circular wait in RAG: P1->R1, R1->P2, P2->R2, R2->P1 ...
        if len(pids) < 2 or len(resources) < 2:
            return
        with self._lock:
            for idx, pid in enumerate(pids):
                req_res = resources[idx % len(resources)]
                hold_res = resources[(idx - 1) % len(resources)]
                self._graph[f"P{pid}"].add(f"R{req_res}")
                self._graph[f"R{hold_res}"].add(f"P{pid}")
