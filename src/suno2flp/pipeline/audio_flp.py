"""Explicit exclusive candidate export; no model, plugin or host invocation."""

import math
import os
import struct
import sys
import wave
from pathlib import Path

from suno2flp.core.audio_flp import DRUM_PREVIEW_KEYS, AudioFlpExport
from suno2flp.core.note_scoring import ScoringRecipe
from suno2flp.core.offline_files import (
    capture_stream_input,
    guarded_path,
    load_unique_json,
    verify_inputs,
)
from suno2flp.core.report_publication import publish_verified_report
from suno2flp.flp_builder.audio_preview import audio_preview_plan, encode_audio_preview
from suno2flp.flp_builder.audio_profile import pinned_components
from suno2flp.flp_builder.preview_samples import percussion_sample
from suno2flp.importer.note_annotations import bounded_snapshot
from suno2flp.integrations.basic_pitch_backend import new_model_directory
from suno2flp.pipeline.estimated_midi import midi_preview_recipe
from suno2flp.validator.audio_flp import verify_audio_preview
from suno2flp.validator.audio_midi_source import load_audio_midi
from suno2flp.validator.percussion_arrangement import Cancel, check_percussion_location
from suno2flp.validator.transcription import check_cancel

README = (
    "Unqualified audio-inference candidate. Open project.flp in FL Studio 26.1.7.5654.\n"
    "Approximate 3x Osc voices and original synthetic percussion; technical 120 BPM / 960 PPQ.\n"
    "Original projected note boundaries are retained; drum keys select one-shot voices at root60.\n"
    "Native volume raw1280 is a preview policy, not a linear amplitude percentage.\n"
    "Reference stems remain in the source audit and are not placed in this FLP.\n"
    "Model, musical tempo/meter/structure, bends, listening and "
    "release qualification remain blocked.\n"
)


def audio_flp_recipe() -> ScoringRecipe:
    base = midi_preview_recipe()
    package = Path(__file__).resolve().parent.parent
    paths = [
        package / p
        for p in (
            "core/audio_flp.py",
            "core/backend_models.py",
            "core/evidence.py",
            "core/errors.py",
            "core/models.py",
            "core/offline_files.py",
            "core/offline_models.py",
            "core/report_publication.py",
            "core/template_inventory.py",
            "core/template_profiles.py",
            "flp_builder/audio_profile.py",
            "flp_builder/audio_preview.py",
            "flp_builder/preview_samples.py",
            "integrations/basic_pitch_backend.py",
            "integrations/template_inventory.py",
            "validator/audio_flp.py",
            "validator/audio_midi_source.py",
            "pipeline/audio_flp.py",
        )
    ]
    for module in (math, struct, wave):
        location = getattr(module, "__file__", None)
        if location is not None:
            paths.append(Path(location))
        elif module.__spec__ is not None and module.__spec__.origin == "built-in":
            runtime = (
                Path(sys.base_prefix)
                / f"python{sys.version_info.major}{sys.version_info.minor}.dll"
                if sys.platform == "win32"
                else Path(sys.executable)
            )
            paths.append(runtime)
        else:
            raise ValueError("Preview runtime module has no current file identity")
    identities = {i.path: i for i in base.files}
    for path in paths:
        i = capture_stream_input(path)
        identities[i.path] = i
    base.files = [identities[p] for p in sorted(identities)]
    return base


def _expected_files(root: Path, source_json: bytes, midi: bytes) -> dict[Path, bytes]:
    return {
        root / "source-midi.json": source_json,
        root / "candidate.mid": midi,
        root / "README.txt": README.encode(),
        **{root / "audio" / f"drum-{key}.wav": percussion_sample(key) for key in DRUM_PREVIEW_KEYS},
    }


def _verify_members(root: Path, expected: set[Path], *, complete: bool) -> None:
    extra = {root / "audio-flp.pending.json"}
    if complete:
        extra.add(root / "audio-flp.json")
    actual = set()
    for path in root.rglob("*"):
        checked = guarded_path(path)
        if checked.is_dir():
            if checked != root / "audio":
                raise ValueError("Unexpected bundle directory")
        else:
            actual.add(checked)
    if actual != expected | extra:
        raise ValueError("Complete bundle membership changed")


def export_audio_flp(
    report: Path, base: Path, sampler: Path, output: Path, *, should_cancel: Cancel = None
) -> AudioFlpExport:
    check_cancel(should_cancel)
    destination = check_percussion_location(output, [report.parent, base.parent, sampler.parent])
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError("Use a new output directory with an existing parent")
    a, raw = bounded_snapshot(base, 1024**2)
    b, sample = bounded_snapshot(sampler, 1024**2)
    profile = pinned_components(raw, sample)
    frozen_recipe = audio_flp_recipe().model_dump_json()
    source, source_id, source_json, protected, recheck = load_audio_midi(report, should_cancel)
    plan = audio_preview_plan(source.score)
    candidate = encode_audio_preview(profile, plan)
    verify_audio_preview(candidate, profile, plan)
    protected = [*protected, a.path.parent, b.path.parent]
    root = new_model_directory(check_percussion_location(destination, protected), protected)
    (root / "audio").mkdir()
    assets = _expected_files(root, source_json, source.midi.path.read_bytes())
    assets[root / "project.flp"] = candidate
    for path, data in assets.items():
        check_cancel(should_cancel)
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    files = [capture_stream_input(path) for path in sorted(assets)]
    result = AudioFlpExport(
        root=root,
        source_report=source_id,
        source_midi=source.midi,
        components=[a, b],
        plan=plan,
        files=files,
        recipe=ScoringRecipe.model_validate_json(frozen_recipe),
        blockers=[
            *source.score.blockers,
            "approximate-preview-instruments",
            "reference-stems-not-in-playlist",
            "song-host-validation-pending",
            "music-and-release-not-qualified",
        ],
    )
    serialized = result.model_dump_json(indent=2)
    frozen_plan = plan.model_dump_json()

    def verify() -> None:
        recheck()
        check_cancel(should_cancel)
        current = AudioFlpExport.model_validate_json(serialized)
        if current.plan.model_dump_json() != frozen_plan or current.recipe != audio_flp_recipe():
            raise ValueError("Candidate plan/recipe changed before publication")
        if plan != audio_preview_plan(source.score):
            raise ValueError("Source projection changed")
        verify_inputs(
            [
                a,
                b,
                source_id,
                source.midi,
                *files,
                current.recipe.python_executable,
                *current.recipe.files,
            ]
        )
        pinned_components(a.path.read_bytes(), b.path.read_bytes())
        for path, data in assets.items():
            if guarded_path(path).read_bytes() != data:
                raise ValueError("Candidate artifact changed")
        verify_audio_preview((root / "project.flp").read_bytes(), profile, plan)
        _verify_members(root, set(assets), complete=False)

    publish_verified_report(root / "audio-flp.json", serialized, protected, verify)
    return result


def verify_audio_flp_export(report: Path, *, should_cancel: Cancel = None) -> AudioFlpExport:
    identity, raw = bounded_snapshot(report, 16 * 1024**2)
    saved = AudioFlpExport.model_validate(load_unique_json(raw))
    root = identity.path.parent
    if (
        identity.path.name != "audio-flp.json"
        or saved.root != root
        or saved.recipe != audio_flp_recipe()
    ):
        raise ValueError("Use the original completed candidate and current recipe")
    source, source_id, source_json, protected, recheck = load_audio_midi(
        saved.source_report.path, should_cancel
    )
    if (
        source_id != saved.source_report
        or source.midi != saved.source_midi
        or saved.plan != audio_preview_plan(source.score)
    ):
        raise ValueError("Candidate source/plan changed")
    a, b = saved.components
    recheck()
    check_cancel(should_cancel)
    verify_inputs(
        [identity, a, b, *saved.files, saved.recipe.python_executable, *saved.recipe.files]
    )
    check_percussion_location(root, [*protected, a.path.parent, b.path.parent])
    profile = pinned_components(a.path.read_bytes(), b.path.read_bytes())
    assets = _expected_files(root, source_json, source.midi.path.read_bytes())
    expected_paths = {*assets, root / "project.flp"}
    if [i.path for i in saved.files] != sorted(expected_paths):
        raise ValueError("Candidate file list changed")
    for path, data in assets.items():
        if guarded_path(path).read_bytes() != data:
            raise ValueError("Candidate bytes changed")
    verify_audio_preview((root / "project.flp").read_bytes(), profile, saved.plan)
    _verify_members(root, expected_paths, complete=True)
    if (root / "audio-flp.pending.json").read_bytes() != raw:
        raise ValueError("Publication documents differ")
    verify_inputs([identity, a, b, *saved.files])
    return saved
