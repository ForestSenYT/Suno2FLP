"""Opt-in actual FL26 negative eligibility: never encode the unresolved user template."""

import hashlib
import os
from pathlib import Path

import mido
import pytest

from suno2flp.arrangement import FaithfulArrangementEngine
from suno2flp.core.build_models import TemplateBindingDocument
from suno2flp.core.errors import FlpWriteError
from suno2flp.core.evidence import snapshot_sha256
from suno2flp.core.models import MusicalMetadata
from suno2flp.core.writer_models import Fl26WriterPolicy
from suno2flp.flp_builder.writer_files import build_fl26_files, plan_fl26_files
from suno2flp.importer import MidiFileImporter
from suno2flp.integrations.music2daw import Music2DawInspector
from suno2flp.integrations.music2daw_provision import verify_backend

pytestmark = pytest.mark.external


def test_actual_unresolved_template_blocks_before_staging_and_stays_unchanged(
    tmp_path, monkeypatch
):
    selected = os.environ.get("SUNO2FLP_FL26_TEMPLATE")
    directory = os.environ.get("SUNO2FLP_MUSIC2DAW_DIR")
    if not selected or not directory:
        pytest.skip(
            "Set SUNO2FLP_FL26_TEMPLATE and SUNO2FLP_MUSIC2DAW_DIR for actual blocking verification"
        )
    source, backend = Path(selected), Path(directory)
    before = source.read_bytes(), source.stat().st_mtime_ns
    backend_before = verify_backend(backend)
    inspection = Music2DawInspector(backend).inspect(source)
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("note_on", channel=2, note=60, velocity=80, time=120),
                mido.Message("note_off", channel=2, note=60, time=240),
            ]
        )
    )
    midi_path = tmp_path / "original-negative-probe.mid"
    midi.save(midi_path)
    arrangement = FaithfulArrangementEngine().arrange(
        [MidiFileImporter().import_file(midi_path)],
        MusicalMetadata(title="Negative eligibility probe only"),
        "faithful",
    )
    bindings = TemplateBindingDocument.model_validate(
        {
            "config": {
                "schema_version": 1,
                "template_sha256": inspection.template_sha256_after,
                "backend_revision": inspection.backend.revision,
                "bindings": [
                    {
                        "source_input": 0,
                        "source_track_position": 0,
                        "source_channel": 2,
                        "template_channel_id": 0,
                        "template_pattern_id": 0,
                        "template_playlist_track": 0,
                    }
                ],
            }
        }
    )
    policy = Fl26WriterPolicy.model_validate(
        {
            "profile": "fl26-26.1.7.5654-write-v1",
            "template_sha256": inspection.template_sha256_after,
            "inventory_snapshot_sha256": snapshot_sha256(inspection.inventory),
            "bindings_snapshot_sha256": snapshot_sha256(bindings.config),
            "reference_kind": "unverified",
            "reviewer": "No review supplied",
            "reference_evidence": "Negative probe only; host/dependency review unverified",
            "dependency_review": "unverified",
            "instrument_review": "unverified",
            "local_use_review": "unverified",
            "content_policy": "replace_all_bound_notes_and_clips",
            "note_attribute_policy": "preserve_reviewed_prototype",
            "clip_extension_policy": "preserve_exact_reference_bytes",
            "targets": [],
        }
    )
    paths = [
        tmp_path / name
        for name in ("arrangement.json", "inspection.json", "bindings.yaml", "policy.yaml")
    ]
    for path, model in zip(paths, (arrangement, inspection, bindings.config, policy), strict=True):
        path.write_text(model.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: pytest.fail("Writer invoked backend"))
    preparation = plan_fl26_files(*paths, backend)
    assert preparation.intent.status == "blocked"
    assert {
        "writer_review_unverified",
        "writer_backend_inconsistent",
        "writer_inventory_incomplete",
        "writer_note_range",
        "writer_note_attributes",
        "writer_crop",
    } <= {d.code for d in preparation.intent.diagnostics}
    output_parent = tmp_path.parent / (tmp_path.name + "-outputs")
    output_parent.mkdir()
    with pytest.raises(FlpWriteError, match="writer_blocked"):
        build_fl26_files(*paths, backend, output_parent / "must-not-exist")
    assert list(output_parent.iterdir()) == []
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert verify_backend(backend) == backend_before
    assert hashlib.sha256(before[0]).hexdigest() == inspection.template_sha256_after
