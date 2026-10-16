"""Real-state workbench; all substantial application I/O runs in one worker."""

import json
from collections.abc import Callable
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from suno2flp.core.errors import OfflineError
from suno2flp.core.job_store import StoredJob
from suno2flp.gui.model import REASONS, STAGES, HistoryEntry, JobActions, present_job
from suno2flp.gui.style import STYLE
from suno2flp.gui.worker import ActionResult, Worker


def label(text: str, name: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


class WorkbenchWindow(QMainWindow):
    def __init__(self, actions: JobActions) -> None:
        super().__init__()
        self.job_actions = actions
        self.selected: StoredJob | None = None
        self.busy = False
        self.last_error = ""
        self._worker: Worker | None = None
        self._close_after = False
        self._cancellable = False
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self.setWindowTitle("Suno2FLP 音频工作台")
        self.setMinimumSize(960, 720)
        self.resize(1220, 860)
        self.setStyleSheet(STYLE)
        canvas = QWidget()
        canvas.setObjectName("Canvas")
        self.setCentralWidget(canvas)
        outer = QHBoxLayout(canvas)
        outer.setContentsMargins(0, 0, 0, 0)
        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(240)
        left = QVBoxLayout(rail)
        left.setContentsMargins(18, 28, 18, 20)
        left.addWidget(label("Suno2FLP", "Brand"))
        left.addWidget(label("本地音频重建工作台"))
        left.addSpacing(20)
        left.addWidget(label("任务保存位置"))
        self.root_edit = QLineEdit(str(actions.root))
        self.root_edit.setAccessibleName("任务保存位置")
        self.root_edit.setToolTip(str(actions.root))
        self.root_edit.editingFinished.connect(self._apply_root)
        left.addWidget(self.root_edit)
        self.root_button = QPushButton("选择任务目录")
        self.root_button.clicked.connect(self._choose_root)
        left.addWidget(self.root_button)
        self.refresh_button = QPushButton("刷新历史任务")
        self.refresh_button.clicked.connect(self.refresh_history)
        left.addWidget(self.refresh_button)
        self.history_list = QListWidget()
        self.history_list.setAccessibleName("历史任务")
        self.history_list.itemActivated.connect(self._history_selected)
        self.history_list.itemClicked.connect(self._history_selected)
        left.addWidget(self.history_list, 1)
        self.env_button = QPushButton("检查运行环境")
        self.env_button.clicked.connect(self.check_environment)
        left.addWidget(self.env_button)
        outer.addWidget(rail)
        right = QVBoxLayout()
        right.setContentsMargins(28, 22, 28, 18)
        right.setSpacing(10)
        right.addWidget(label("音频工作台", "Title"))
        right.addWidget(label("研发预览：当前可检查 PCM WAV，完整转换仍在开发。", "Muted"))
        inputs = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("选择一首音频，原文件会保持不变")
        self.source_edit.setAccessibleName("输入音频路径")
        inputs.addWidget(self.source_edit, 1)
        self.source_button = QPushButton("选择音频")
        self.source_button.clicked.connect(self._choose_source)
        inputs.addWidget(self.source_button)
        self.create_button = QPushButton("创建任务")
        self.create_button.clicked.connect(self._create_from_field)
        inputs.addWidget(self.create_button)
        right.addLayout(inputs)
        self.task_title = label("从一首音频开始", "Subtitle")
        right.addWidget(self.task_title)
        self.status = label("尚未创建任务", "Status")
        right.addWidget(self.status)
        self.explanation = label("选择音频并创建任务，然后开始检查。历史记录保存在左侧所选目录。")
        right.addWidget(self.explanation)
        self.summary = label("0 / 11 个阶段完成", "Muted")
        right.addWidget(self.summary)
        self.stages = QTableWidget(len(STAGES), 3)
        self.stages.setHorizontalHeaderLabels(["流程", "阶段", "状态"])
        self.stages.verticalHeader().hide()
        self.stages.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stages.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.stages.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.stages.setColumnWidth(0, 48)
        self.stages.setColumnWidth(2, 110)
        for row, name in enumerate(STAGES):
            for col, value in enumerate((str(row + 1), name, "待执行")):
                self.stages.setItem(row, col, QTableWidgetItem(value))
            self.stages.setRowHeight(row, 28)
        right.addWidget(self.stages, 1)
        buttons = QHBoxLayout()
        self.run_button = QPushButton("开始检查 / 恢复")
        self.run_button.setObjectName("Primary")
        self.run_button.clicked.connect(self.run_selected)
        self.verify_button = QPushButton("核验来源与结果")
        self.verify_button.clicked.connect(self.verify_selected)
        self.cancel_button = QPushButton("取消检查")
        self.cancel_button.clicked.connect(self.cancel_selected)
        for button in (self.run_button, self.verify_button, self.cancel_button):
            buttons.addWidget(button)
        buttons.addStretch()
        right.addLayout(buttons)
        self.activity = QProgressBar()
        self.activity.setRange(0, 1)
        self.activity.setTextVisible(False)
        right.addWidget(self.activity)
        self.notice = label("尚未生成工程；宿主兼容性和音乐质量未经验证。", "Notice")
        right.addWidget(self.notice)
        self.details_button = QToolButton()
        self.details_button.setText("来源与诊断")
        self.details_button.setCheckable(True)
        right.addWidget(self.details_button)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(130)
        self.details.hide()
        self.details_button.toggled.connect(self.details.setVisible)
        right.addWidget(self.details)
        outer.addLayout(right, 1)
        self._controls()

    def _controls(self) -> None:
        for widget in (
            self.root_edit,
            self.root_button,
            self.refresh_button,
            self.history_list,
            self.env_button,
            self.source_edit,
            self.source_button,
            self.create_button,
        ):
            widget.setEnabled(not self.busy)
        view = present_job(self.selected) if self.selected else None
        self.run_button.setEnabled(not self.busy and view is not None and view.can_run)
        self.verify_button.setEnabled(not self.busy and view is not None)
        self.cancel_button.setEnabled(
            self._cancellable if self.busy else view is not None and view.can_cancel
        )
        self.activity.setRange(0, 0 if self.busy else 1)

    def _submit(
        self, action: Callable[[Event], ActionResult], *, cancellable: bool = False
    ) -> None:
        if self.busy:
            return
        self.busy = True
        self.last_error = ""
        self._cancellable = cancellable
        self.notice.setText("正在核对文件，请稍候。")
        self._worker = Worker(action)
        self._worker.signals.completed.connect(self._completed)
        self._controls()
        self._pool.start(self._worker)

    @Slot(object, object)
    def _completed(self, result: object, error: object) -> None:
        self.busy = False
        self._worker = None
        if isinstance(error, Exception):
            self.last_error = str(error)
            reason = REASONS.get(error.code) if isinstance(error, OfflineError) else None
            self.notice.setText(reason or "操作未完成。请查看诊断，核对文件路径及访问权限。")
            self.details.setPlainText(str(error))
            self.details_button.setChecked(True)
        elif isinstance(result, ActionResult):
            if result.stored is not None:
                self.selected = result.stored
                view = present_job(result.stored)
                self.task_title.setText(view.title)
                self.status.setText(view.status)
                self.explanation.setText(view.explanation)
                self.summary.setText(f"{view.completed} / {view.total} 个阶段完成")
                self.details.setPlainText(view.diagnostics)
                for row, (_, status) in enumerate(view.stages):
                    self.stages.setItem(row, 2, QTableWidgetItem(status))
            if result.history is not None:
                self.history_list.clear()
                for entry in result.history:
                    item = QListWidgetItem(f"{entry.title}\n{entry.status}")
                    item.setToolTip(entry.error or str(entry.root))
                    item.setData(Qt.ItemDataRole.UserRole, entry)
                    self.history_list.addItem(item)
            self.notice.setText(result.notice or "记录已保存。完整转换与质量验收尚未完成。")
            if result.diagnostics is not None:
                self.details.setPlainText(result.diagnostics)
                self.details_button.setChecked(True)
        self._controls()
        if self._close_after:
            self.close()

    def create_job(self, source: Path) -> None:
        actions = self.job_actions

        def create(cancel: Event) -> ActionResult:
            stored = actions.create(source)
            if cancel.is_set():
                stored = actions.cancel(stored.record.path)
            return ActionResult(stored=stored, history=tuple(actions.history()))

        self._submit(create, cancellable=True)

    def load_snapshot(self, path: Path) -> None:
        actions = self.job_actions
        self._submit(lambda _: ActionResult(stored=actions.load(path)))

    def run_selected(self) -> None:
        if self.selected is None:
            return
        actions, snapshot = self.job_actions, self.selected.record.path
        self._submit(
            lambda cancel: ActionResult(
                stored=actions.run(snapshot, cancel), history=tuple(actions.history())
            ),
            cancellable=True,
        )

    def verify_selected(self) -> None:
        if self.selected is None:
            return
        actions, snapshot = self.job_actions, self.selected.record.path
        self._submit(
            lambda _: ActionResult(
                stored=actions.verify(snapshot),
                notice="当前文件与独立预检证据一致；完整转换、宿主和音乐质量尚未验收。",
            )
        )

    def cancel_selected(self) -> None:
        if self.busy:
            if self._worker is not None and self._cancellable:
                self._worker.cancel.set()
                self.notice.setText("正在请求停止；当前只读检查到达安全边界后停止。")
            return
        if self.selected is not None:
            actions, snapshot = self.job_actions, self.selected.record.path
            self._submit(
                lambda _: ActionResult(
                    stored=actions.cancel(snapshot), history=tuple(actions.history())
                )
            )

    def refresh_history(self) -> None:
        actions = self.job_actions
        self._submit(
            lambda _: ActionResult(
                history=tuple(actions.history()),
                notice="历史任务已读取。选择任务后可检查当前文件。",
            )
        )

    def check_environment(self) -> None:
        actions = self.job_actions

        def check(_: Event) -> ActionResult:
            checks = actions.environment()
            return ActionResult(
                notice="环境清单已读取。找到安装文件不代表宿主或插件已验证。",
                diagnostics=json.dumps(
                    [item.model_dump() for item in checks], ensure_ascii=False, indent=2
                ),
            )

        self._submit(check)

    def set_workspace(self, path: Path, *, refresh: bool = True) -> bool:
        if self.busy:
            return False
        try:
            actions = JobActions(path)
        except (OfflineError, OSError, ValueError) as error:
            self.notice.setText(f"任务目录不可用：{error}")
            return False
        self.job_actions = actions
        self.selected = None
        self.root_edit.setText(str(actions.root))
        self.root_edit.setToolTip(str(actions.root))
        self.task_title.setText("选择一个历史任务，或创建新任务")
        self.status.setText("尚未选择任务")
        self.explanation.setText("任务只会保存在当前所选目录中。")
        self.summary.setText("0 / 11 个阶段完成")
        self.details.clear()
        for row in range(len(STAGES)):
            self.stages.setItem(row, 2, QTableWidgetItem("待执行"))
        self.history_list.clear()
        if refresh:
            self.refresh_history()
        return True

    def _apply_root(self) -> None:
        if self.root_edit.text() != str(self.job_actions.root):
            self.set_workspace(Path(self.root_edit.text()), refresh=False)

    def _choose_root(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择任务目录", str(self.job_actions.root))
        if chosen:
            self.set_workspace(Path(chosen))

    def _choose_source(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "选择音频", "", "音频 (*.wav *.mp3 *.flac)")
        if chosen:
            self.source_edit.setText(chosen)
            self.source_edit.setToolTip(chosen)

    def _create_from_field(self) -> None:
        if not self.source_edit.text().strip():
            self.notice.setText("请先选择输入音频。")
            return
        if self.root_edit.text() != str(self.job_actions.root) and not self.set_workspace(
            Path(self.root_edit.text()), refresh=False
        ):
            return
        self.create_job(Path(self.source_edit.text()))

    def _history_selected(self, item: QListWidgetItem) -> None:
        entry = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, HistoryEntry):
            if entry.snapshot is not None:
                self.load_snapshot(entry.snapshot)
            else:
                self.selected = None
                self.task_title.setText(entry.title)
                self.status.setText("记录不可读")
                self.summary.setText("阶段状态无法核验")
                self.explanation.setText("记录已保留。请查看诊断，使用原素材创建新任务。")
                for row in range(len(STAGES)):
                    self.stages.setItem(row, 2, QTableWidgetItem("无法核验"))
                self.notice.setText("此任务记录不完整或损坏，已保留。请查看诊断并创建新任务。")
                self.details.setPlainText(entry.error or str(entry.root))
                self.details_button.setChecked(True)
                self._controls()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.busy:
            self._close_after = True
            if self._worker is not None:
                self._worker.cancel.set()
            self.notice.setText("正在停止当前操作，保存记录后关闭。")
            event.ignore()
        else:
            event.accept()
