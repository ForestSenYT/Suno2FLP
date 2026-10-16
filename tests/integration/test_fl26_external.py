"""Opt-in private, user-owned FL26 input; never copy, save or rewrite the project."""

import hashlib
import os
from pathlib import Path

import pytest

from suno2flp.core.backend_models import TemplateInspectionReport
from suno2flp.integrations.music2daw import Music2DawInspector
from suno2flp.integrations.music2daw_provision import verify_backend

pytestmark = pytest.mark.external


def test_user_selected_fl26_template_is_read_only_and_backend_comparison_is_honest():
    template = os.environ.get("SUNO2FLP_FL26_TEMPLATE")
    backend = os.environ.get("SUNO2FLP_MUSIC2DAW_DIR")
    if not template or not backend:
        pytest.skip(
            "Set SUNO2FLP_FL26_TEMPLATE and SUNO2FLP_MUSIC2DAW_DIR for private FL26 validation"
        )
    path, directory = Path(template), Path(backend)
    before, stat = path.read_bytes(), path.stat()
    _, backend_before = verify_backend(directory)
    result = Music2DawInspector(directory).inspect(path)
    assert result.inventory.fl_studio_version == "26.1.7.5654"
    assert result.inventory.profile_id == "fl26-26.1.7.5654-read-v1"
    assert result.inventory.notes and result.inventory.clips
    assert {clip.record_size for clip in result.inventory.clips} == {88}
    overrides = [event for event in result.inventory.events if event.event_id == 172]
    assert overrides and all(
        e.payload_size == 3 and e.framing_rule == "fl26-event-172-3bytes" for e in overrides
    )
    assert result.local_summary.playlist_item_count == len(result.inventory.clips)
    assert result.local_summary.pattern_note_counts is not None
    assert sum(result.local_summary.pattern_note_counts.values()) == len(result.inventory.notes)
    assert result.backend_summary_status == "inconsistent" and result.backend_summary_mismatches
    assert result.compatibility == "unverified"
    assert TemplateInspectionReport.model_validate_json(result.model_dump_json()) == result
    assert (
        result.template_sha256_before
        == result.template_sha256_after
        == hashlib.sha256(before).hexdigest()
    )
    assert path.read_bytes() == before and path.stat().st_mtime_ns == stat.st_mtime_ns
    assert verify_backend(directory)[1] == backend_before
