from __future__ import annotations

import random
import threading
import time

from kernel import Kernel
from process.process import ProcessState
from syscalls import (
    sys_create_process,
    sys_log_event,
    sys_request_seat,
)


def buyer_worker(kernel: Kernel, pid: int, category: str) -> None:
    # User-space process issues syscalls only; direct kernel module access is blocked by design.
    attempts = 0
    while attempts < 6 and not kernel.seat_manager.is_exhausted():
        requested = category if attempts == 0 else random.choice(["VIP", "Gold", "Silver"])
        sys_request_seat(kernel, pid, requested, caller_role="user")
        time.sleep(random.uniform(0.003, 0.015))
        proc = kernel.process_manager.get_process(pid)
        if not proc or proc.state == ProcessState.TERMINATED:
            return
        if proc.allocated_seat:
            kernel.run_scheduler_step()
            return
        attempts += 1


def scheduler_daemon(kernel: Kernel) -> None:
    idle_ticks = 0
    while not kernel.seat_manager.is_exhausted() and kernel.process_manager.count_active() > 0:
        pid = kernel.run_scheduler_step()
        if pid is None:
            idle_ticks += 1
            time.sleep(0.005)
            if idle_ticks > 2000:
                break
        else:
            idle_ticks = 0


def deadlock_scenario(kernel: Kernel, pids: list[int]) -> None:
    # Inject synthetic circular waits to exercise RAG detection + recovery path.
    if len(pids) >= 4:
        kernel.deadlock_manager.generate_synthetic_deadlock(pids[:4], ["VIP", "Gold", "Silver", "VIP"])


def memory_pressure_test(kernel: Kernel, pids: list[int]) -> None:
    sample = pids[: min(80, len(pids))]
    if sample:
        stats = kernel.memory_manager.simulate_thrashing(sample, rounds=500)
        sys_log_event(kernel, "thrashing_test", details=stats, caller_role="kernel")


def main() -> None:
    scheduler_algorithm = random.choice(["FCFS", "SJF", "ROUND_ROBIN", "PRIORITY"])
    kernel = Kernel(scheduler_algorithm=scheduler_algorithm)
    kernel.boot()
    sys_log_event(kernel, "boot_complete", details={"scheduler": scheduler_algorithm}, caller_role="kernel")

    buyer_threads: list[threading.Thread] = []
    pids: list[int] = []
    seat_choices = ["VIP", "Gold", "Silver"]

    # Spawn enough user processes to exhaust seat inventory with heavy contention.
    for _ in range(500):
        seat = random.choice(seat_choices)
        priority = random.randint(1, 10)
        burst = random.uniform(0.004, 0.02)
        pages = random.randint(1, 8)
        pid = sys_create_process(kernel, seat, priority, burst, pages, caller_role="user")
        pids.append(pid)
        t = threading.Thread(target=buyer_worker, args=(kernel, pid, seat), daemon=True)
        buyer_threads.append(t)
        t.start()

    deadlock_scenario(kernel, pids)
    memory_pressure_test(kernel, pids)
    metrics = kernel.run_parallel_metrics()
    sys_log_event(kernel, "parallel_metrics_done", details=metrics, caller_role="kernel")

    sched_thread = threading.Thread(target=scheduler_daemon, args=(kernel,), daemon=True)
    sched_thread.start()

    for thread in buyer_threads:
        thread.join(timeout=0.2)
    sched_thread.join(timeout=15)
    kernel.sys_event_queue.join()

    # Demonstrate file manager disk scheduling.
    requests = [random.randint(0, 199) for _ in range(20)]
    order, movement = kernel.file_manager.schedule_requests(requests, algorithm=random.choice(["FCFS", "SSTF", "SCAN"]))
    sys_log_event(kernel, "disk_schedule", details={"order": order, "movement": movement}, caller_role="kernel")

    final_seats = kernel.seat_manager.available()
    bookings = kernel.storage.load_bookings()
    print("=== TICKET OPERATING SYSTEM (TOS) SIMULATION ===")
    print(f"Scheduler: {scheduler_algorithm}")
    print(f"Total processes created: {len(pids)}")
    print(f"Total bookings: {len(bookings)}")
    print(f"Remaining seats: {final_seats}")
    print(f"Seat exhausted: {kernel.seat_manager.is_exhausted()}")

    kernel.shutdown()


if __name__ == "__main__":
    main()
