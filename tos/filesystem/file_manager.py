import math
from pathlib import Path
from typing import Iterable


class FileManager:
    """Simple file system and disk scheduling simulator."""

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root) if root else Path(__file__).resolve().parents[1] / "data"
        self.root.mkdir(parents=True, exist_ok=True)

    def read(self, filename: str) -> str:
        path = self.root / filename
        path.touch(exist_ok=True)
        return path.read_text(encoding="utf-8")

    def write(self, filename: str, content: str) -> None:
        path = self.root / filename
        path.write_text(content, encoding="utf-8")

    def append(self, filename: str, content: str) -> None:
        path = self.root / filename
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)

    def log(self, message: str) -> None:
        self.append("kernel_fs.log", message + "\n")

    def schedule_requests(
        self,
        requests: Iterable[int],
        algorithm: str = "FCFS",
        head: int = 50,
        max_track: int = 199,
    ) -> tuple[list[int], int]:
        req = list(requests)
        if not req:
            return [], 0
        algo = algorithm.upper()
        if algo == "FCFS":
            order = req
        elif algo == "SSTF":
            order = []
            pending = req[:]
            cursor = head
            while pending:
                nearest = min(pending, key=lambda x: abs(x - cursor))
                pending.remove(nearest)
                order.append(nearest)
                cursor = nearest
        elif algo == "SCAN":
            left = sorted([r for r in req if r < head], reverse=True)
            right = sorted([r for r in req if r >= head])
            order = right + [max_track] + left
        else:
            raise ValueError(f"Unsupported disk scheduling algorithm: {algorithm}")

        movement = 0
        cursor = head
        for track in order:
            movement += math.fabs(track - cursor)
            cursor = track
        return order, int(movement)
