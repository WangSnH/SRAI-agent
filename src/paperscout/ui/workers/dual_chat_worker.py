from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from paperscout.services.dual_orchestrator import run_dual_turn


class _ChatSignalRelay(QObject):
    """Lives on main thread; relays signals safely from worker thread."""
    progress = Signal(str)
    finished = Signal(str)
    failed = Signal(str)


class DualChatWorker(QObject):
    progress = Signal(str)
    finished = Signal(str)   # final answer (OpenAI)
    failed = Signal(str)

    def __init__(self, settings: dict, history: list, user_text: str, init_meta: dict | None = None):
        super().__init__()
        self.settings = settings
        self.history = history
        self.user_text = user_text
        self.init_meta = init_meta or {}

    def run(self):
        try:
            self.progress.emit("▶ 正在构建上下文并发送给 OpenAI…")
            final, _deep = run_dual_turn(
                settings=self.settings,
                history=self.history,
                user_text=self.user_text,
                init_meta=self.init_meta,
            )
            self.progress.emit("▶ OpenAI 正在生成回复…")
            self.finished.emit(final or "（OpenAI 返回为空）")
        except Exception as e:
            self.failed.emit(str(e))


def start_dual_chat(settings: dict, history: list, user_text: str, init_meta: dict,
                    on_progress, on_ok, on_err):
    thread = QThread()
    worker = DualChatWorker(settings, history, user_text, init_meta=init_meta)
    worker.moveToThread(thread)

    relay = _ChatSignalRelay()
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
