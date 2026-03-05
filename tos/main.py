from __future__ import annotations

from collections import Counter
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


def print_process_report(kernel: Kernel, pids: list[int], bookings: list[dict[str, object]]) -> None:
    logs = kernel.storage.read_logs()
    events = Counter(entry.get("event", "unknown") for entry in logs)
    termination_reasons = Counter(
        (entry.get("details") or {}).get("reason", "unknown")
        for entry in logs
        if entry.get("event") == "process_terminated"
    )
    scheduled_counts = Counter(
        entry.get("process_id")
        for entry in logs
        if entry.get("event") == "scheduled" and entry.get("process_id") is not None
    )
    table = kernel.process_manager.process_table
    state_counts = Counter(proc.state.value for proc in table.values())
    booked_by_pid = {int(row["process_id"]): str(row["seat_category"]) for row in bookings}
    waiting_pids = sorted(pid for pid, proc in table.items() if proc.state == ProcessState.WAITING)
    ready_pids = sorted(pid for pid, proc in table.items() if proc.state == ProcessState.READY)
    running_pid = kernel.process_manager.running_process

    print("Process lifecycle:")
    print(
        "  states -> "
        + ", ".join(
            f"{name}: {state_counts.get(name, 0)}"
            for name in ("NEW", "READY", "RUNNING", "WAITING", "TERMINATED")
        )
    )
    print(
        "  terminations -> "
        + ", ".join(
            f"{reason}: {count}"
            for reason, count in sorted(termination_reasons.items(), key=lambda x: (-x[1], x[0]))
        )
        if termination_reasons
        else "  terminations -> none"
    )
    print(
        f"  scheduler dispatches: {events.get('scheduled', 0)} "
        f"(unique pids dispatched: {len(scheduled_counts)})"
    )
    if scheduled_counts:
        top = sorted(scheduled_counts.items(), key=lambda x: (-x[1], int(x[0])))[:8]
        print("  top scheduled pids: " + ", ".join(f"PID {int(pid)} ({count}x)" for pid, count in top))
    print(
        "  seat requests -> "
        f"allocated: {events.get('seat_allocated', 0)}, waiting: {events.get('seat_wait', 0)}, "
        f"released: {events.get('seat_released', 0)}"
    )
    print(
        "  queues -> "
        f"ready: {len(ready_pids)}, waiting: {len(waiting_pids)}, "
        f"running: {running_pid if running_pid is not None else 'none'}"
    )
    if waiting_pids:
        preview = ", ".join(str(pid) for pid in waiting_pids[:20])
        suffix = " ..." if len(waiting_pids) > 20 else ""
        print(f"  waiting pids (first 20): {preview}{suffix}")

    print("Sample process table (first 12 pids):")
    for pid in pids[:12]:
        proc = table.get(pid)
        if not proc:
            continue
        booked = booked_by_pid.get(pid, "-")
        allocated = proc.allocated_seat or "-"
        print(
            f"  PID {pid:>3} | pri={proc.priority:>2} | want={proc.required_seat:<6} | "
            f"state={proc.state.value:<10} | allocated={allocated:<6} | booked={booked}"
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
    print_process_report(kernel, pids, bookings)

    kernel.shutdown()


if __name__ == "__main__":
    main()
