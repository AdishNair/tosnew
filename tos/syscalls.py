from __future__ import annotations

from typing import Any

from kernel import Kernel


def sys_create_process(
    kernel: Kernel,
    required_seat: str,
    priority: int,
    burst_time: float,
    pages_required: int,
    caller_role: str = "user",
) -> int:
    kernel.authorize("sys_create_process", caller_role)
    return kernel.create_process(required_seat, priority, burst_time, pages_required, role=caller_role)


def sys_request_seat(kernel: Kernel, pid: int, category: str, caller_role: str = "user") -> None:
    kernel.authorize("sys_request_seat", caller_role)
    kernel.enqueue_event({"type": "request_seat", "pid": pid, "category": category})


def sys_release_seat(kernel: Kernel, pid: int, caller_role: str = "admin") -> bool:
    kernel.authorize("sys_release_seat", caller_role)
    return kernel.release_seat(pid)


def sys_log_event(kernel: Kernel, event: str, pid: int | None = None, details: dict[str, Any] | None = None, caller_role: str = "user") -> None:
    kernel.authorize("sys_log_event", caller_role)
    kernel.enqueue_event({"type": "log", "event": event, "pid": pid, "details": details or {}})


def sys_terminate_process(kernel: Kernel, pid: int, caller_role: str = "admin") -> None:
    kernel.authorize("sys_terminate_process", caller_role)
    kernel.enqueue_event({"type": "terminate", "pid": pid, "reason": "syscall_terminate"})
