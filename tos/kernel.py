from __future__ import annotations

import multiprocessing
import queue
import random
import threading
import time
from typing import Any

from deadlock.deadlock_manager import DeadlockManager
from filesystem.file_manager import FileManager
from memory.memory_manager import MemoryManager
from process.process import ProcessState
from process.process_manager import ProcessManager
from resources.seat_manager import SeatManager
from scheduler.scheduler import Scheduler
from storage.storage import StorageBackend
from utils.logger import Logger


def _parallel_metrics_worker(sample_size: int) -> dict[str, float]:
    random.seed(sample_size)
    values = [random.random() for _ in range(sample_size)]
    return {"sample_size": float(sample_size), "mean": sum(values) / max(len(values), 1)}


class Kernel:
    """Microkernel coordinator: only accessible through syscalls wrapper."""

    def __init__(self, scheduler_algorithm: str = "FCFS", reset_storage: bool = True) -> None:
        self.storage = StorageBackend()
        if reset_storage:
            self.storage.reset_for_boot()
        self.file_manager = FileManager()
        self.logger = Logger(self.storage)
        self.process_manager = ProcessManager()
        self.scheduler = Scheduler(scheduler_algorithm)
        self.seat_manager = SeatManager(self.storage)
        self.deadlock_manager = DeadlockManager()
        self.memory_manager = MemoryManager()
        self.sys_event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stop_event = threading.Event()
        self._event_thread = threading.Thread(target=self._event_loop, daemon=True, name="tos-kernel-events")
        self._deadlock_thread = threading.Thread(target=self._deadlock_monitor, daemon=True, name="tos-deadlock-monitor")
        self._scheduler_lock = threading.Lock()
        self._security = {
            "sys_create_process": {"user", "admin", "kernel"},
            "sys_request_seat": {"user", "admin", "kernel"},
            "sys_release_seat": {"admin", "kernel"},
            "sys_log_event": {"user", "admin", "kernel"},
            "sys_terminate_process": {"admin", "kernel"},
        }

    def boot(self) -> None:
        self.logger.log("system_boot")
        self._event_thread.start()
        self._deadlock_thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        self.sys_event_queue.put({"type": "noop"})
        self._event_thread.join(timeout=2)
        self._deadlock_thread.join(timeout=2)
        self.logger.log("system_shutdown")
        self.logger.shutdown()

    def authorize(self, syscall_name: str, role: str) -> None:
        allowed = self._security.get(syscall_name, {"kernel"})
        if role not in allowed:
            raise PermissionError(f"Role '{role}' is not allowed to call {syscall_name}")

    def create_process(self, required_seat: str, priority: int, burst_time: float, pages_required: int, role: str) -> int:
        proc = self.process_manager.create_process(
            required_seat=required_seat,
            priority=priority,
            burst_time=burst_time,
            pages_required=pages_required,
            role=role,
        )
        allocated = self.memory_manager.allocate(proc.pid, pages_required, replacement_algo=random.choice(["FIFO", "LRU", "OPTIMAL"]))
        self.logger.log("process_created", proc.pid, {"memory_allocated": allocated, "seat": required_seat})
        return proc.pid

    def request_seat(self, pid: int, category: str) -> bool:
        proc = self.process_manager.get_process(pid)
        if not proc or proc.state == ProcessState.TERMINATED:
            return False
        # Prevent duplicate allocations when repeated requests for same PID arrive concurrently.
        if proc.allocated_seat is not None:
            return True
        self.deadlock_manager.add_request(pid, category)
        ok = self.seat_manager.allocate_seat(pid, category)
        if ok:
            proc.allocated_seat = category
            self.deadlock_manager.grant(pid, category)
            self.process_manager.set_ready(pid)
            self.logger.log("seat_allocated", pid, {"category": category})
        else:
            self.process_manager.set_waiting(pid)
            self.logger.log("seat_wait", pid, {"category": category})
        return ok

    def release_seat(self, pid: int) -> bool:
        proc = self.process_manager.get_process(pid)
        if not proc:
            return False
        seat = proc.allocated_seat
        ok = self.seat_manager.release_seat(pid)
        if seat:
            self.deadlock_manager.release(pid, seat)
        if ok:
            proc.allocated_seat = None
            self.process_manager.set_ready(pid)
            self.logger.log("seat_released", pid, {})
        return ok

    def terminate_process(self, pid: int, reason: str = "normal_exit") -> bool:
        proc = self.process_manager.terminate_process(pid)
        if not proc:
            return False
        if proc.allocated_seat:
            if reason == "ticket_booked":
                self.seat_manager.consume_allocation(pid)
            else:
                self.seat_manager.release_seat(pid)
                self.deadlock_manager.release(pid, proc.allocated_seat)
            proc.allocated_seat = None
        self.memory_manager.release(pid)
        self.logger.log("process_terminated", pid, {"reason": reason})
        return True

    def run_scheduler_step(self) -> int | None:
        with self._scheduler_lock:
            ready = self.process_manager.get_ready_processes()
            selected = self.scheduler.pick_next(ready)
            if not selected:
                return None
            self.process_manager.set_running(selected.pid)
            self.logger.log("scheduled", selected.pid, {"algorithm": self.scheduler.algorithm})
            time.sleep(min(self.scheduler.time_quantum, selected.pcb.burst_time))
            # Context-switch simulation.
            time.sleep(0.002)
            if selected.allocated_seat:
                self.terminate_process(selected.pid, reason="ticket_booked")
            else:
                self.process_manager.set_ready(selected.pid)
            return selected.pid

    def enqueue_event(self, event: dict[str, Any]) -> None:
        self.sys_event_queue.put(event)

    def _event_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                event = self.sys_event_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            etype = event.get("type")
            if etype == "request_seat":
                self.request_seat(event["pid"], event["category"])
            elif etype == "terminate":
                self.terminate_process(event["pid"], reason=event.get("reason", "external"))
            elif etype == "log":
                self.logger.log(event.get("event", "custom"), event.get("pid"), event.get("details"))
            self.sys_event_queue.task_done()

    def _deadlock_monitor(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(0.1)
            has_cycle, cycle_path = self.deadlock_manager.detect_deadlock()
            categories, available, alloc, max_need = self.seat_manager.snapshot_for_banker()
            banker_safe = self.deadlock_manager.bankers_safe_state(categories, available, alloc, max_need)
            if has_cycle or not banker_safe:
                active = list(self.process_manager.iter_active())
                victim = self.deadlock_manager.resolve_by_terminating_lowest_priority(active)
                if victim is not None:
                    self.terminate_process(victim, reason="deadlock_recovery")
                    self.logger.log("deadlock_recovered", victim, {"cycle": cycle_path, "banker_safe": banker_safe})

    def run_parallel_metrics(self) -> dict[str, float]:
        with multiprocessing.Pool(processes=2) as pool:
            results = pool.map(_parallel_metrics_worker, [1000, 1500])
        mean_of_means = sum(r["mean"] for r in results) / len(results)
        payload = {"mean_of_means": mean_of_means, "workers": float(len(results))}
        self.logger.log("parallel_metrics", details=payload)
        return payload
