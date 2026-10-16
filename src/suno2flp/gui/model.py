"""Qt-independent presentation and actions over the authoritative job service."""

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from uuid import uuid4

from suno2flp.core.doctor import EnvironmentCheck, check_environment
from suno2flp.core.errors import OfflineError
from suno2flp.core.job_store import StoredJob
from suno2flp.core.offline_files import guarded_path
from suno2flp.pipeline.audio_jobs import (
    cancel_audio_job,
    create_audio_job,
    run_audio_job,
    verify_audio_job,
)
from suno2flp.pipeline.job_store import latest_job, load_job

STATUS = {
    "queued": "待执行",
    "running": "检查中",
    "blocked": "已阻断",
    "failed": "检查失败",
    "cancelled": "已取消",
    "succeeded": "已完成",
}
STAGES = (
    "音频检查",
    "音频解码",
    "分轨分离",
    "速度与结构",
    "音符转写",
    "轨道编排",
    "音源与路由",
    "生成工程",
    "宿主验证",
    "质量验收",
    "交付结果",
)
REASONS = {
    "worker_unavailable": "音频已解码并复核。分轨分离尚未接入，当前没有生成 FLP。",
    "audio_format_unavailable": "此音频格式尚未接入。当前支持整数 PCM WAV 和限定的 FLAC、MP3。",
    "audio_codec_unavailable": "此编码不在已验证范围内。请查看音频格式限制，并保留原文件。",
    "audio_backend_unavailable": "压缩音频解码器尚未准备或未指定。请先完成固定运行时准备。",
    "audio_python_unavailable": "当前应用运行环境不在压缩解码器的固定版本范围内。",
    "audio_platform_unavailable": "当前系统不在已验证的压缩音频解码范围内。",
    "audio_backend_integrity_failed": "解码器文件与固定清单不一致。请在新目录重新准备运行时。",
    "audio_timing_unavailable": "此 MP3 缺少已验证的起点和尾部时序证据，暂不能保持原始时序。",
    "audio_worker_unavailable": "隔离解码进程无法启动，候选结果不能继续使用。",
    "audio_worker_failed": "隔离解码未通过，失败记录已保留。",
    "audio_worker_timeout": "隔离解码进程超时，候选结果未标记完成。",
    "audio_worker_output_limit": "解码诊断超出上限，候选结果未标记完成。",
    "audio_wheel_missing": "缺少固定版本的离线安装包，请先准备完整的解码器依赖。",
    "audio_wheel_integrity_failed": "安装包与固定哈希不符，不能加载该解码器。",
    "audio_worker_diagnostic": "原生解码器报告了未确认的诊断，候选结果已阻断。",
    "audio_worker_cleanup_failed": "解码进程未能确认退出，不能把此次尝试视为完成。",
    "audio_invalid": "音频文件损坏或结构不完整。请重新导出完整文件，并创建新任务。",
    "audio_limits_exceeded": "音频超出当前支持范围。请查看格式、声道、时长和大小限制。",
    "offline_input_changed": "输入文件发生变化。为保留来源，请使用当前素材创建新任务。",
    "audio_io_failed": "无法读取音频或保存检查结果。请检查路径及文件权限。",
    "audio_decode_timeout": "音频解码或逐样本复核超时，候选文件已保留，未标记完成。",
    "audio_runtime_changed": "解码运行环境发生变化。旧结果无法复用，请创建新任务。",
    "audio_runtime_unavailable": "当前环境不支持已验证的音频解码表示。请查看环境诊断。",
    "audio_decode_sample_mismatch": "解码样本与原始音频不一致，结果不能继续使用。",
    "audio_decode_evidence_invalid": "解码证据不完整或与当前文件不一致，结果不能继续使用。",
    "user_cancelled": "检查已取消。已有记录保留，可在文件身份一致时恢复检查。",
    "interrupted": "上次检查中断。已有记录保留，可重新检查。",
}


@dataclass(frozen=True)
class JobView:
    title: str
    status: str
    explanation: str
    completed: int
    total: int
    stages: tuple[tuple[str, str], ...]
    can_run: bool
    can_cancel: bool
    diagnostics: str


@dataclass(frozen=True)
class HistoryEntry:
    root: Path
    title: str
    status: str
    snapshot: Path | None
    error: str | None = None


def present_job(stored: StoredJob) -> JobView:
    job = stored.job
    code = next((event.code for event in reversed(job.history) if event.code), None)
    explanation = REASONS.get(code or "", "任务记录已载入；输入和结果尚未在本次会话中复核。")
    if job.status == "queued":
        explanation = "任务已创建。开始检查将只读核对音频，并保存实际结果。"
    elif job.status == "running":
        explanation = "上次检查尚未记录结束。恢复会保留中断记录，重新核对文件。"
    return JobView(
        title=job.source.path.stem,
        status="待检查" if job.status == "queued" else STATUS[job.status],
        explanation=explanation,
        completed=sum(stage.status == "succeeded" for stage in job.stages),
        total=len(job.stages),
        stages=tuple(
            (name, STATUS[stage.status]) for name, stage in zip(STAGES, job.stages, strict=True)
        ),
        can_run=job.status != "succeeded",
        can_cancel=job.status in ("queued", "running"),
        diagnostics=stored.model_dump_json(indent=2),
    )


class JobActions:
    def __init__(self, root: Path, decoder_directory: Path | None = None) -> None:
        self.root = guarded_path(root)
        self.decoder_directory = (
            guarded_path(decoder_directory) if decoder_directory is not None else None
        )

    def create(self, source: Path) -> StoredJob:
        if any((parent / "backend.json").exists() for parent in (self.root, *self.root.parents)):
            raise OfflineError("job_output_unsafe", "任务目录必须在后端安装目录之外")
        self.root.mkdir(parents=True, exist_ok=True)
        identifier = "audio-" + uuid4().hex
        return create_audio_job(source, self.root / identifier, identifier)

    def history(self) -> list[HistoryEntry]:
        root = guarded_path(self.root)
        if not root.exists():
            return []
        entries = []
        for path in sorted(root.iterdir(), reverse=True):
            if not (path / "states").exists() and not path.name.startswith("audio-"):
                continue
            try:
                stored = latest_job(path)
                view = present_job(stored)
                entries.append(HistoryEntry(path, view.title, view.status, stored.record.path))
            except (OfflineError, OSError, ValueError) as error:
                entries.append(HistoryEntry(path, path.name, "记录不可读", None, str(error)))
        return entries

    def _owned(self, snapshot: Path) -> StoredJob:
        stored = load_job(snapshot)
        if stored.job.output_directory.parent != self.root:
            raise OfflineError("job_output_unsafe", "请选择当前任务目录中的记录")
        return stored

    def load(self, snapshot: Path) -> StoredJob:
        return latest_job(self._owned(snapshot).job.output_directory)

    def run(self, snapshot: Path, cancel: Event) -> StoredJob:
        self._owned(snapshot)
        return run_audio_job(
            snapshot, should_cancel=cancel.is_set, decoder_directory=self.decoder_directory
        )

    def verify(self, snapshot: Path) -> StoredJob:
        self._owned(snapshot)
        return verify_audio_job(snapshot)

    def cancel(self, snapshot: Path) -> StoredJob:
        self._owned(snapshot)
        return cancel_audio_job(snapshot)

    def environment(self) -> list[EnvironmentCheck]:
        return check_environment()
