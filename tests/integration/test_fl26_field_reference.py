"""Opt-in host-reference readback; never encodes, writes or distributes private FLPs."""

import os
from pathlib import Path

import pytest

from suno2flp.core.fl26_fields import note_attribute_form, pattern_crop_observation
from suno2flp.flp_builder.assessment import assess_template
from suno2flp.integrations.music2daw import Music2DawInspector
from suno2flp.integrations.music2daw_provision import verify_backend

pytestmark = pytest.mark.external


@pytest.mark.parametrize(
    "name,position,length,crop_form,start,end,forms",
    [
        ("positive", 0, 384, "default_sentinel", None, None, ["ordinary", "ordinary"]),
        ("left-crop", 96, 288, "explicit_ticks", 96, 384, ["ordinary", "ordinary"]),
        ("both-crop", 96, 192, "explicit_ticks", 96, 288, ["ordinary", "ordinary"]),
        ("slide", 96, 192, "explicit_ticks", 96, 288, ["slide", "ordinary"]),
    ],
)
def test_private_gui_references_match_field_observations_without_modification(
    name, position, length, crop_form, start, end, forms
):
    selected = os.environ.get("SUNO2FLP_FL26_REFERENCE_DIR")
    backend_dir = os.environ.get("SUNO2FLP_FL26_ADAPTED_BACKEND")
    if not selected or not backend_dir:
        pytest.skip("Set SUNO2FLP_FL26_REFERENCE_DIR and SUNO2FLP_FL26_ADAPTED_BACKEND")
    path = Path(selected) / f"user-reference-fl26-{name}-v1.flp"
    if not path.is_file():
        pytest.fail(f"Explicitly selected host-reference prerequisite is missing: {path}")
    backend = Path(backend_dir)
    original = path.read_bytes(), path.stat().st_mtime_ns
    backend_before = verify_backend(backend)
    report = Music2DawInspector(backend).inspect(path)
    assert report.project.fl_studio_version == "26.1.7.5654"
    assert report.project.tempo == 120 and report.header.ppq == 96
    assert report.backend_summary_status == "consistent"
    inventory = report.inventory
    assert inventory is not None and len(inventory.clips) == 1
    assert [(n.pitch, n.position_ticks, n.length_ticks, n.velocity) for n in inventory.notes] == [
        (60, 0, 96, 100),
        (64, 192, 96, 100),
    ]
    assert [note_attribute_form(n, inventory.profile_id) for n in inventory.notes] == forms
    clip = inventory.clips[0]
    assert (clip.position_ticks, clip.length_ticks) == (position, length)
    crop = pattern_crop_observation(clip, inventory.profile_id)
    assert crop is not None and (crop.form, crop.start_ticks, crop.end_ticks) == (
        crop_form,
        start,
        end,
    )
    assessment = assess_template(original[0], report)
    assert assessment.execution_allowed is False and assessment.compatibility == "unverified"
    assert ("note_attributes_unresolved" in {f.code for f in assessment.findings}) == (
        name == "slide"
    )
    assert (path.read_bytes(), path.stat().st_mtime_ns) == original
    assert verify_backend(backend) == backend_before
