"""One bounded application operation; Qt signals deliver results to the UI thread."""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal

from suno2flp.core.job_store import StoredJob
from suno2flp.gui.model import HistoryEntry


@dataclass(frozen=True)
class ActionResult:
    stored: StoredJob | None = None
    history: tuple[HistoryEntry, ...] | None = None
    notice: str = ""
    diagnostics: str | None = None


class WorkerSignals(QObject):
    completed = Signal(object, object)


class Worker(QRunnable):
    def __init__(self, action: Callable[[Event], ActionResult]) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self.cancel = Event()
        self.action = action

    def run(self) -> None:
        try:
            result = self.action(self.cancel)
        except Exception as error:
            self.signals.completed.emit(None, error)
        else:
            self.signals.completed.emit(result, None)
