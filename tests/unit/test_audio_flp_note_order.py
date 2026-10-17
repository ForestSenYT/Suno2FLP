"""Native scheduling order is derived; source occurrence/tick audit stays unchanged."""

import struct

import pytest
from test_audio_flp import fixtures

from suno2flp.core.audio_flp import AudioPreviewNote, AudioPreviewPlan
from suno2flp.flp_builder.audio_preview import encode_audio_preview
from suno2flp.flp_builder.audio_profile import components
from suno2flp.integrations.template_inventory import scan_template_inventory
from suno2flp.validator.audio_flp import verify_audio_preview


def unordered_case():
    def pitched(part, occurrence, stem, channel, pitch, start):
        return AudioPreviewNote(
            source_part=part,
            source_occurrence=occurrence,
            stem=stem,
            channel=channel,
            source_pitch=pitch,
            pitch=pitch,
            start_tick=start,
            end_tick=start + 480,
        )

    notes = [
        pitched(0, 2, "vocals", 0, 67, 1920),
        pitched(2, 0, "other", 2, 72, 960),
        pitched(0, 1, "vocals", 0, 64, 960),
        pitched(0, 0, "vocals", 0, 60, 960),
        pitched(1, 0, "bass", 1, 36, 960),
        AudioPreviewNote(
            source_part=3,
            source_occurrence=0,
            stem="drums",
            channel=7,
            source_pitch=36,
            pitch=60,
            start_tick=480,
            end_tick=576,
        ),
    ]
    return components(*fixtures()), AudioPreviewPlan(
        source_score_sha256="0" * 64, notes=notes, end_tick=11520
    )


def test_native_storage_orders_ticks_channels_and_occurrences_without_changing_source():
    profile, plan = unordered_case()
    before = plan.model_dump_json()
    raw = encode_audio_preview(profile, plan)
    inv = scan_template_inventory(raw)
    order = [5, 3, 2, 4, 1, 0]
    assert [(n.position_ticks, n.channel_id, n.pitch, n.length_ticks) for n in inv.notes] == [
        (
            plan.notes[i].start_tick,
            plan.notes[i].channel,
            plan.notes[i].pitch,
            plan.notes[i].end_tick - plan.notes[i].start_tick,
        )
        for i in order
    ]
    assert plan.model_dump_json() == before
    verify_audio_preview(raw, profile, plan)


def test_independent_verifier_rejects_same_complete_notes_in_reverse_storage_order():
    profile, plan = unordered_case()
    raw = encode_audio_preview(profile, plan)
    inv = scan_template_inventory(raw)
    (event,) = [e for e in inv.events if e.event_id == 224]
    rows = [
        raw[i : i + 24]
        for i in range(event.payload_offset, event.payload_offset + event.payload_size, 24)
    ]
    rows = sorted(
        rows, key=lambda r: (struct.unpack_from("<I", r)[0], struct.unpack_from("<H", r, 6)[0])
    )
    rows.reverse()
    mutated = (
        raw[: event.payload_offset]
        + b"".join(rows)
        + raw[event.payload_offset + event.payload_size :]
    )
    with pytest.raises(ValueError):
        verify_audio_preview(mutated, profile, plan)


def test_current_profile_declares_native_order_and_observed_audible_gain():
    profile, plan = unordered_case()
    assert plan.profile == "fl26-audio-candidate-v2"
    assert plan.note_storage_order == "start-tick-channel-source-part-occurrence-v1"
    assert plan.channel_gain == 5000
    raw = encode_audio_preview(profile, plan)
    inv = scan_template_inventory(raw)
    gains = [
        struct.unpack_from("<I", raw, e.payload_offset + 4)[0]
        for e in inv.events
        if e.event_id == 219
    ]
    assert gains == [5000] * 12
    with pytest.raises(ValueError):
        AudioPreviewPlan.model_validate({**plan.model_dump(), "profile": "fl26-audio-candidate-v1"})
