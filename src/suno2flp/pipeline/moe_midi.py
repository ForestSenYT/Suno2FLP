"""Exclusive inferred-program MIDI files, retained source guards, completion last."""

import os
import platform
import sys
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

import mido
import pydantic

from suno2flp.arrangement.moe_midi import encode_moe_part, project_moe_midi
from suno2flp.core.moe_midi import MoEMidiChannel, MoEMidiExport, MoEMidiFile, MoEMidiInputs
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.offline_models import FileIdentity
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.core.yourmt3_moe import YourMT3MoECandidate
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.integrations.yourmt3_backend import yourmt3_adapters
from suno2flp.integrations.yourmt3_source import load_yourmt3_moe_pins
from suno2flp.validator.moe_midi import verify_moe_part
from suno2flp.validator.transcription import check_cancel
from suno2flp.validator.yourmt3_moe import VerifiedMoESource, collect_verified_moe

Cancel = Callable[[], bool] | None
COMPANION = (
    "未验收的音频推断 MIDI 候选，不能视为官方 MIDI、音乐质量合格或 FLP。\n"
    "每个模型通道／程序独立一个 MIDI，原地址／标签仅作元数据；需单独选择音源。\n"
    "模型程序100是 Singing Voice，不代表 GM100。没有写入 GM 程序、CC、弯音或拍号。\n"
    "960PPQ／500000微秒是音频秒的技术时钟，不是识别出的120BPM或4/4。\n"
    "音符边界独立就近半向上取整；原始 binary64、音符次序、动态及精确误差在报告中。\n"
    "发声速度固定96，不能视为原曲动态。音乐、路由、宿主、GUI及写入资格仍阻断。\n"
)


def moe_midi_recipe() -> ScoringRecipe:
    paths = {i.path for i in yourmt3_adapters()}
    paths.update(Path(mido.__file__).resolve().parent.rglob("*.py"))
    return ScoringRecipe(
        python_executable=capture_stream_input(Path(sys.executable)),
        python_version=platform.python_version(),
        pydantic_version=pydantic.__version__,
        files=[capture_stream_input(p) for p in sorted(paths)],
    )


def _location(output: Path, protected: list[Path]) -> Path:
    target = guarded_path(output)
    for source in protected:
        source = guarded_path(source)
        if target.is_relative_to(source) or source.is_relative_to(target):
            raise ValueError("MIDI output overlaps immutable source/backend evidence")
    if any((parent / "backend.json").exists() for parent in (target, *target.parents)):
        raise ValueError("MIDI output cannot be inside a backend")
    return target


def _early_source(report: Path) -> tuple[FileIdentity, list[Path]]:
    identity, raw = bounded_snapshot(report, 1024**2)
    candidate = YourMT3MoECandidate.model_validate(load_unique_json(raw))
    if identity.path.name != "yourmt3-moe.json" or candidate.root != identity.path.parent:
        raise ValueError("Use the original complete MoE producer report")
    return identity, [
        candidate.root,
        candidate.backend.path.parent,
        candidate.decode_report.path.parent,
        candidate.source_audio.path,
        candidate.pcm.path,
    ]


def _load(
    report: Path, *, should_cancel: Cancel
) -> tuple[MoEMidiInputs, VerifiedMoESource, list[Path]]:
    receipt = collect_verified_moe(report, should_cancel=should_cancel)
    native, backend = receipt.native, receipt.backend
    inputs = MoEMidiInputs(
        producer=receipt.producer.model_copy(deep=True),
        candidate=receipt.candidate,
        model_channels=[
            MoEMidiChannel(
                channel=c.channel,
                notes=c.notes,
                decode_errors=c.decode_errors,
                merge_errors=c.merge_errors,
            )
            for c in native.channels
        ],
        program_channels=load_yourmt3_moe_pins().program_channels,
    )
    _, protected = _early_source(report)
    protected += [
        backend.root,
        *[
            i.path
            for i in [backend.python, *backend.runtime, *backend.artifacts, *backend.adapters]
        ],
    ]
    return inputs, receipt, protected


def _name(channel: int, program: int) -> str:
    return f"modelch-{channel:02d}-program-{program:03d}.mid"


def _write(path: Path, raw: bytes) -> FileIdentity:
    with guarded_path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return capture_stream_input(path)


def _verify_outputs(record: MoEMidiExport, *, completed: bool, should_cancel: Cancel) -> None:
    root = guarded_path(record.root)
    expected_root = {"notes", "README.zh-CN.txt", "moe-midi.pending.json"}
    if completed:
        expected_root.add("moe-midi.json")
    if {guarded_path(p).name for p in root.iterdir()} != expected_root:
        raise ValueError("MIDI bundle directory inventory differs from complete publication layout")
    expected_names = {_name(p.source_channel, p.model_program) for p in record.score.parts}
    notes = guarded_path(root / "notes")
    if {guarded_path(p).name for p in notes.iterdir()} != expected_names:
        raise ValueError("MIDI part inventory changed, is missing or contains extras")
    if record.companion.path != root / "README.zh-CN.txt":
        raise ValueError("MIDI companion path changed")
    actual, raw = bounded_snapshot(record.companion.path, 65536)
    if actual != record.companion or raw != COMPANION.encode("utf-8"):
        raise ValueError("MIDI companion bytes changed")
    if len(record.files) != len(record.score.parts):
        raise ValueError("Retain every complete model-program file exactly once")
    for part, item in zip(record.score.parts, record.files, strict=True):
        check_cancel(should_cancel)
        path = notes / _name(part.source_channel, part.model_program)
        if (item.source_channel, item.model_program, item.midi.path) != (
            part.source_channel,
            part.model_program,
            path,
        ):
            raise ValueError("MIDI model-program source addresses or file paths changed")
        actual, raw = bounded_snapshot(path, 8 * 1024**2)
        if actual != item.midi:
            raise ValueError("MIDI output identity changed")
        verify_moe_part(raw, part, record.score.end_tick)


def export_moe_midi(report: Path, output: Path, *, should_cancel: Cancel = None) -> MoEMidiExport:
    check_cancel(should_cancel)
    producer, early_protected = _early_source(report)
    destination = _location(output, early_protected)
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError("Use a new MIDI bundle directory with an existing parent")
    recipe = moe_midi_recipe().model_dump_json()
    inputs, receipt, protected = _load(producer.path, should_cancel=should_cancel)
    if inputs.producer != producer:
        raise ValueError("MoE producer changed while loading source evidence")
    score = project_moe_midi(inputs)
    frozen_score, frozen_backend = score.model_dump_json(), receipt.backend.model_dump_json()
    check_cancel(should_cancel)
    root = new_model_directory(_location(output, protected), protected)
    (root / "notes").mkdir()
    files = []
    for part in score.parts:
        check_cancel(should_cancel)
        raw = encode_moe_part(part, score.end_tick)
        verify_moe_part(raw, part, score.end_tick)
        identity = _write(root / "notes" / _name(part.source_channel, part.model_program), raw)
        files.append(
            MoEMidiFile(
                source_channel=part.source_channel, model_program=part.model_program, midi=identity
            )
        )
    companion = _write(root / "README.zh-CN.txt", COMPANION.encode("utf-8"))
    record = MoEMidiExport(
        root=root,
        score=score,
        files=files,
        companion=companion,
        source_backend=receipt.backend,
        recipe=ScoringRecipe.model_validate_json(recipe),
        mido_version=version("mido"),
    )
    serialized = record.model_dump_json(indent=2)

    def verify() -> None:
        saved = MoEMidiExport.model_validate_json(serialized)
        if (
            saved.score.model_dump_json() != frozen_score
            or saved.source_backend.model_dump_json() != frozen_backend
            or saved.recipe.model_dump_json() != recipe
            or saved.recipe != moe_midi_recipe()
            or saved.mido_version != version("mido")
        ):
            raise ValueError("Frozen source, MIDI projection or current recipe changed")
        _verify_outputs(saved, completed=False, should_cancel=should_cancel)
        receipt.recheck(should_cancel=should_cancel)
        verify_inputs(
            [
                saved.companion,
                *[f.midi for f in saved.files],
                saved.recipe.python_executable,
                *saved.recipe.files,
            ]
        )
        check_cancel(should_cancel)

    publish_verified_report(root / "moe-midi.json", serialized, protected, verify)
    return record


def verify_moe_midi_export(report: Path, *, should_cancel: Cancel = None) -> MoEMidiExport:
    check_cancel(should_cancel)
    identity, raw = bounded_snapshot(report, 16 * 1024**2)
    saved = MoEMidiExport.model_validate(load_unique_json(raw))
    if identity.path.name != "moe-midi.json" or saved.root != identity.path.parent:
        raise ValueError("Use the completed MIDI bundle in its original directory")
    if saved.recipe != moe_midi_recipe() or saved.mido_version != version("mido"):
        raise ValueError("MIDI export implementation or runtime changed")
    inputs, receipt, protected = _load(
        saved.score.inputs.producer.path, should_cancel=should_cancel
    )
    _location(saved.root, protected)
    if (
        saved.score.model_dump_json() != project_moe_midi(inputs).model_dump_json()
        or saved.source_backend.model_dump_json() != receipt.backend.model_dump_json()
    ):
        raise ValueError("Saved MIDI score differs from complete current native source")
    _verify_outputs(saved, completed=True, should_cancel=should_cancel)
    pending, pending_raw = bounded_snapshot(saved.root / "moe-midi.pending.json", 16 * 1024**2)
    if pending_raw != raw:
        raise ValueError("Pending and completed MIDI manifest bytes differ")
    receipt.recheck(should_cancel=should_cancel)
    verify_inputs(
        [
            identity,
            pending,
            saved.companion,
            *[f.midi for f in saved.files],
            saved.recipe.python_executable,
            *saved.recipe.files,
        ]
    )
    check_cancel(should_cancel)
    return saved
