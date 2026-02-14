from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from paperscout.services.openai_init import submit_init_prompt


class _OpenAIInitRelay(QObject):
    """Lives on main thread; relays signals safely from worker thread."""
    finished = Signal(str)
    failed = Signal(str)


class OpenAIInitWorker(QObject):
    """Run the fixed OpenAI init prompt in a worker thread."""

    finished = Signal(str)  # reply text
    failed = Signal(str)    # error message

    def __init__(self, settings: dict):
        super().__init__()
        self._settings = settings

    def run(self):
        try:
            text = submit_init_prompt(self._settings)
            self.finished.emit(text)
        except Exception as e:
            self.failed.emit(str(e))


def start_openai_init(settings: dict, on_ok, on_err):
    """Convenience: start a QThread and wire signals.

    Returns (thread, worker, relay). Keep references to prevent GC.
    """
    thread = QThread()
    worker = OpenAIInitWorker(settings)
    worker.moveToThread(thread)

    relay = _OpenAIInitRelay()
    worker.finished.connect(relay.finished)
    worker.failed.connect(relay.failed)

    relay.finished.connect(on_ok)
    relay.failed.connect(on_err)

    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)

    thread.start()
    return thread, worker, relay
