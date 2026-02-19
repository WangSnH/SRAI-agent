from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from paperscout.services.zh2en_orchestrator import run_zh2en_turn


class _Zh2EnChatRelay(QObject):
    progress = Signal(str)
    finished = Signal(str, dict)
    failed = Signal(str)


class Zh2EnChatWorker(QObject):
    progress = Signal(str)
    finished = Signal(str, dict)
    failed = Signal(str)

    def __init__(self, settings: dict, history: list, user_text: str, init_meta: dict | None = None):
        super().__init__()
        self.settings = settings
        self.history = history
        self.user_text = user_text
        self.init_meta = init_meta or {}

    def run(self):
        try:
            self.progress.emit("▶ 正在执行中译英模型调用…")
            output = run_zh2en_turn(
                settings=self.settings,
                history=self.history,
                user_text=self.user_text,
                init_meta=self.init_meta,
            )
            output = output if isinstance(output, dict) else {}
            final = str(output.get("final_answer") or "").strip() or "（中译英返回为空）"
            updated_meta = output.get("updated_init_meta") if isinstance(output.get("updated_init_meta"), dict) else {}
            self.finished.emit(final, updated_meta)
        except Exception as e:
            self.failed.emit(str(e))


def start_zh2en_chat(settings: dict, history: list, user_text: str, init_meta: dict, on_progress, on_ok, on_err):
    thread = QThread()
    worker = Zh2EnChatWorker(settings, history, user_text, init_meta=init_meta)
    worker.moveToThread(thread)

    relay = _Zh2EnChatRelay()
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
