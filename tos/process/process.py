from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class ProcessState(str, Enum):
    NEW = "NEW"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    TERMINATED = "TERMINATED"


@dataclass
class PCB:
    pid: int
    priority: int
    required_seat: str
    state: ProcessState = ProcessState.NEW
    arrival_time: float = field(default_factory=time.time)
    burst_time: float = 0.0
    pages_required: int = 1
    role: str = "user"


class Process:
    def __init__(
        self,
        pid: int,
        priority: int,
        required_seat: str,
        burst_time: float,
        pages_required: int,
        role: str = "user",
    ) -> None:
        self.pcb = PCB(
            pid=pid,
            priority=priority,
            required_seat=required_seat,
            state=ProcessState.NEW,
            burst_time=burst_time,
            pages_required=pages_required,
            role=role,
        )
        self.allocated_seat: str | None = None
        self.completed = False

    @property
    def pid(self) -> int:
        return self.pcb.pid

    @property
    def priority(self) -> int:
        return self.pcb.priority

    @property
    def required_seat(self) -> str:
        return self.pcb.required_seat

    @property
    def state(self) -> ProcessState:
        return self.pcb.state

    def set_state(self, state: ProcessState) -> None:
        self.pcb.state = state
