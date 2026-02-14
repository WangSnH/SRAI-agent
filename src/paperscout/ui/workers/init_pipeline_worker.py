from __future__ import annotations

from time import perf_counter

from PySide6.QtCore import QObject, QThread, Signal

from paperscout.services.init_pipeline import build_steps, make_summary
from paperscout.services.init_steps.base import InitContext


class _SignalRelay(QObject):
    """Lives on main thread; relays signals safely from worker thread."""
    progress = Signal(str)
    finished = Signal(str, dict)
    failed = Signal(str)


class InitPipelineWorker(QObject):
    progress = Signal(str)
    finished = Signal(str, dict)  # summary, ctx.data
    failed = Signal(str)

    def __init__(self, settings: dict, feature_key: str, thread_id: str, thread_name: str, original_input: str = ""):
        super().__init__()
        self.settings = settings
        self.feature_key = feature_key
        self.thread_id = thread_id
        self.thread_name = thread_name
        self.original_input = original_input

    def run(self):
        try:
            ctx = InitContext(
                settings=self.settings,
                feature_key=self.feature_key,
                thread_id=self.thread_id,
                thread_name=self.thread_name,
                original_input=self.original_input,
            )

            steps = build_steps()
            total = len(steps)
            self.progress.emit(f"开始初始化管线（共 {total} 步）…")

            for i, step in enumerate(steps, start=1):
                step_name = getattr(step, "name", step.__class__.__name__)
                self.progress.emit(f"▶ ({i}/{total}) {step_name} …")

                t0 = perf_counter()
                try:
                    step.run(ctx)
                except Exception as e:
                    ms = int((perf_counter() - t0) * 1000)
                    self.progress.emit(f"❌ ({i}/{total}) {step_name} 失败（{ms}ms）：{e}")
                    self.failed.emit(f"{step_name} 失败：{e}")
                    return

                ms = int((perf_counter() - t0) * 1000)
                self.progress.emit(f"✅ ({i}/{total}) {step_name} 完成（{ms}ms）")

            self.progress.emit("✅ 初始化管线全部完成。")
            self.finished.emit(make_summary(ctx), ctx.data)

        except Exception as e:
            self.failed.emit(str(e))


def start_init_pipeline(settings: dict, feature_key: str, thread_id: str, thread_name: str,
                        original_input: str,
                        on_progress, on_ok, on_err):
    thread = QThread()
    worker = InitPipelineWorker(settings, feature_key, thread_id, thread_name, original_input=original_input)
    worker.moveToThread(thread)

    # 信号中继：worker(工作线程) → relay(QObject 主线程) → 回调(主线程)
    # 因为两端都是 QObject，AutoConnection 能正确解析为 QueuedConnection
    relay = _SignalRelay()
    worker.progress.connect(relay.progress)
    worker.finished.connect(relay.finished)
    worker.failed.connect(relay.failed)

    # relay 在主线程 emit，回调也在主线程执行
    relay.progress.connect(on_progress)
    relay.finished.connect(on_ok)
    relay.failed.connect(on_err)

    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)

    thread.start()
    return thread, worker, relay
