import json
import threading
from pathlib import Path
from typing import Any


class StorageBackend:
    """JSON-backed persistence for seats, bookings, and logs."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._lock = threading.Lock()
        self.base_path = Path(base_dir) if base_dir else Path(__file__).resolve().parents[1] / "data"
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.seats_file = self.base_path / "seats.json"
        self.bookings_file = self.base_path / "bookings.json"
        self.logs_file = self.base_path / "logs.json"
        self._ensure_files()

    def _ensure_files(self) -> None:
        if not self.seats_file.exists():
            self._write_json(self.seats_file, {"VIP": 50, "Gold": 100, "Silver": 200})
        if not self.bookings_file.exists():
            self._write_json(self.bookings_file, [])
        if not self.logs_file.exists():
            self._write_json(self.logs_file, [])

    def _read_json(self, path: Path) -> Any:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, payload: Any) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def load_seats(self) -> dict[str, int]:
        with self._lock:
            return self._read_json(self.seats_file)

    def save_seats(self, seats: dict[str, int]) -> None:
        with self._lock:
            self._write_json(self.seats_file, seats)

    def load_bookings(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_json(self.bookings_file)

    def append_booking(self, booking: dict[str, Any]) -> None:
        with self._lock:
            data = self._read_json(self.bookings_file)
            data.append(booking)
            self._write_json(self.bookings_file, data)

    def append_log(self, log_entry: dict[str, Any]) -> None:
        with self._lock:
            data = self._read_json(self.logs_file)
            data.append(log_entry)
            self._write_json(self.logs_file, data)

    def read_logs(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_json(self.logs_file)

    def reset_for_boot(self) -> None:
        with self._lock:
            self._write_json(self.seats_file, {"VIP": 50, "Gold": 100, "Silver": 200})
            self._write_json(self.bookings_file, [])
            self._write_json(self.logs_file, [])
