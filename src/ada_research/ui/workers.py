"""QThread worker objects for background work.

Uses the modern QObject-moved-to-QThread pattern (not QThread subclassing).
Each worker emits `finished(result)` on success and `failed(message)` on error.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QObject, pyqtSignal


class GenericWorker(QObject):
    """Run any callable on a background thread.

    Signals:
        finished(object): emitted with the callable's return value on success
        failed(str): emitted with an error message on exception
    """

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")
            return
        self.finished.emit(result)


class PipelineWorker(QObject):
    """Specialized worker for Stage 1 pipeline execution.

    Same pattern as GenericWorker but with progress signal hooks for the UI.
    """

    started = pyqtSignal()
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)  # Stage1Results
    failed = pyqtSignal(str)

    def __init__(self, source: Path | str | None = None, text: str | None = None,
                 sector_name: str | None = None):
        super().__init__()
        self._source = source
        self._text = text
        self._sector_name = sector_name

    def run(self) -> None:
        from ada_research.core.pipeline import (
            run_pipeline_on_pdf,
            run_pipeline_on_text,
        )
        self.started.emit()
        try:
            if self._source is not None:
                self.progress.emit("Extracting PDF text…")
                result = run_pipeline_on_pdf(self._source)
            else:
                self.progress.emit("Scoring text…")
                result = run_pipeline_on_text(
                    self._text or "", sector_name=self._sector_name
                )
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")
            return
        self.progress.emit("Done.")
        self.finished.emit(result)


def run_in_thread(parent_widget, worker: QObject, on_finished, on_failed=None):
    """Helper: move worker to a QThread, wire up signals, start it.

    The thread is parented to `parent_widget` so it gets cleaned up on close.
    Returns the thread so the caller can hold a reference.
    """
    from PyQt6.QtCore import QThread

    thread = QThread(parent_widget)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(on_finished)
    if on_failed is not None:
        worker.failed.connect(on_failed)
    worker.finished.connect(thread.quit)
    if hasattr(worker, "failed"):
        worker.failed.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread
