from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from paperscout.services.zh2en_orchestrator import run_zh2en_init


class _Zh2EnInitRelay(QObject):
    progress = Signal(str)
    finished = Signal(str, dict)
    failed = Signal(str)


class Zh2EnInitWorker(QObject):
    progress = Signal(str)
    finished = Signal(str, dict)
    failed = Signal(str)

    def __init__(self, settings: dict, thread_name: str, original_input: str):
        super().__init__()
        self.settings = settings
        self.thread_name = thread_name
        self.original_input = original_input

    def run(self):
        try:
            self.progress.emit("初始化 1/1")
            data = run_zh2en_init(
                settings=self.settings,
                thread_name=self.thread_name,
                original_input=self.original_input,
            )
            summary = str((data or {}).get("zh2en_init_reply") or "").strip() or "中译英初始化完成。"
            self.finished.emit(summary, data if isinstance(data, dict) else {})
        except Exception as e:
            self.failed.emit(str(e))


def start_zh2en_init_pipeline(settings: dict, thread_name: str, original_input: str, on_progress, on_ok, on_err):
    thread = QThread()
    worker = Zh2EnInitWorker(settings=settings, thread_name=thread_name, original_input=original_input)
    worker.moveToThread(thread)

    relay = _Zh2EnInitRelay()
    worker.progress.connect(relay.progress)
    worker.finished.connect(relay.finished)
    worker.failed.connect(relay.failed)

    relay.progress.connect(on_progress)
    relay.finished.connect(on_ok)
    relay.failed.connect(on_err)

    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)

    thread.start()
    return thread, worker, relay
