"""Original tiny FL26 fixtures and independent output mutation checks."""

import struct

import pytest
from test_fl26_inventory import event, project
from test_percussion_arrangement import inputs

from suno2flp.arrangement.midi_preview import project_estimated_midi
from suno2flp.arrangement.percussion import build_percussion_arrangement
from suno2flp.core.errors import Suno2FLPError
from suno2flp.flp_builder.audio_preview import audio_preview_plan, encode_audio_preview
from suno2flp.flp_builder.audio_profile import components
from suno2flp.integrations.template_inventory import scan_template_inventory
from suno2flp.validator.audio_flp import verify_audio_preview


def fixtures():
    note = struct.pack("<IHHIHH8B", 0, 0x4000, 0, 96, 60, 0, 120, 0, 64, 0, 64, 96, 128, 128)
    clip = bytearray(88)
    struct.pack_into("<IHHIHH", clip, 0, 0, 20480, 20481, 768, 499, 0)
    struct.pack_into("<H", clip, 18, 64)
    struct.pack_into("<I", clip, 28, 768)
    clip[72:80] = b"opaque!!"
    prefix = event(199, b"26.1.7.5654\0") + event(156, struct.pack("<I", 120000)) + event(9, b"\1")
    prefix += event(65, b"\1\0") + event(224, note)
    synth = event(64, b"\0\0") + event(21, b"\2") + event(201, "3x Osc\0".encode("utf-16-le"))
    synth += event(213, b"original opaque oscillator state") + event(
        203, "Reference\0".encode("utf-16-le")
    )
    synth += (
        event(0, b"\1")
        + event(132, struct.pack("<I", 65537))
        + event(219, struct.pack("<6I", 6400, 10000, 0, 256, 0, 0))
    )
    sampler = event(64, b"\1\0") + event(21, b"\0") + event(203, "Sampler\0".encode("utf-16-le"))
    sampler += (
        event(0, b"\1")
        + event(132, b"\0" * 4)
        + event(219, struct.pack("<6I", 6400, 10000, 0, 256, 0, 0))
    )
    sampler += event(196, "old.wav\0".encode("utf-16-le")) + event(
        215, b"original opaque sampler parameters"
    )
    suffix = event(99, b"\0\0") + event(233, clip) + event(225, b"original untouched mixer state")
    base = bytearray(project(prefix + synth + suffix))
    struct.pack_into("<H", base, 10, 1)
    donor = bytearray(project(prefix + synth + sampler + suffix))
    struct.pack_into("<H", donor, 10, 2)
    return bytes(base), bytes(donor)


def case():
    base, donor = fixtures()
    profile = components(base, donor)
    score = project_estimated_midi(build_percussion_arrangement(inputs()))
    return profile, score, audio_preview_plan(score)


def test_every_occurrence_keeps_projected_ticks_and_source_audit():
    profile, score, plan = case()
    original = score.model_dump_json()
    raw = encode_audio_preview(profile, plan)
    verify_audio_preview(raw, profile, plan)
    assert score.model_dump_json() == original
    inv = scan_template_inventory(raw)
    assert inv.ppq == 960 and inv.channel_count == 12 and len(inv.notes) == 5
    assert [(n.position_ticks, n.length_ticks) for n in inv.notes] == [
        (n.start_tick, n.end_tick - n.start_tick)
        for n in sorted(
            plan.notes,
            key=lambda n: (n.start_tick, n.channel, n.source_part, n.source_occurrence),
        )
    ]
    assert inv.clips[0].length_ticks >= score.end_tick + 3840
    assert inv.clips[0].raw_hex[144:160] == b"opaque!!".hex()
    for n in plan.notes:
        source = score.parts[n.source_part].notes[n.source_occurrence]
        assert (n.start_tick, n.end_tick, n.source_pitch) == (
            source.start.tick,
            source.end.tick,
            source.pitch,
        )
        assert n.pitch == (60 if n.stem == "drums" else source.pitch)
    assert plan.status == "unqualified_candidate" and plan.legacy_writer_eligibility == "blocked"


@pytest.mark.parametrize("field", ["opaque", "note", "channel", "tempo", "crop", "trailing"])
def test_independent_verifier_rejects_mutations(field):
    profile, _, plan = case()
    raw = bytearray(encode_audio_preview(profile, plan))
    inv = scan_template_inventory(bytes(raw))
    if field == "opaque":
        e = next(e for e in inv.events if e.event_id == 213)
        raw[e.payload_offset] ^= 1
    elif field == "note":
        raw[inv.notes[0].file_offset + 8] ^= 1
    elif field == "channel":
        e = next(e for e in inv.events if e.event_id == 64)
        raw[e.payload_offset] ^= 1
    elif field == "tempo":
        e = next(e for e in inv.events if e.event_id == 156)
        raw[e.payload_offset] ^= 1
    elif field == "crop":
        raw[inv.clips[0].file_offset + 28] ^= 1
    else:
        raw.extend(b"junk")
    with pytest.raises((ValueError, Suno2FLPError)):
        verify_audio_preview(bytes(raw), profile, plan)


def test_wrong_components_and_tampered_plan_are_rejected():
    profile, score, plan = case()
    score.parts[0].notes[0].start.tick += 1
    with pytest.raises(ValueError):
        audio_preview_plan(score)
    broken = bytearray(profile.base)
    broken[-1] ^= 1
    from suno2flp.flp_builder.audio_profile import pinned_components

    with pytest.raises(ValueError, match="pinned"):
        pinned_components(bytes(broken), profile.sampler)
    plan.notes[0] = plan.notes[0].model_copy(update={"end_tick": plan.notes[0].start_tick})
    with pytest.raises(ValueError):
        encode_audio_preview(profile, plan)


@pytest.mark.parametrize("identifier", [224, 233])
def test_partial_selected_record_payload_is_never_silently_ignored(identifier):
    profile, _, plan = case()
    raw = encode_audio_preview(profile, plan)
    inv = scan_template_inventory(raw)
    records = []
    for e in inv.events:
        if e.event_id == identifier:
            records.append(
                event(identifier, raw[e.payload_offset : e.payload_offset + e.payload_size] + b"\0")
            )
        else:
            records.append(raw[e.file_offset : e.payload_offset + e.payload_size])
    body = b"".join(records)
    changed = raw[:18] + struct.pack("<I", len(body)) + body
    with pytest.raises((ValueError, Suno2FLPError)):
        verify_audio_preview(changed, profile, plan)


def test_noncanonical_replacement_header_is_rejected():
    profile, _, plan = case()
    raw = encode_audio_preview(profile, plan)
    inv = scan_template_inventory(raw)
    e = next(e for e in inv.events if e.event_id == 219)
    assert e.payload_size == 24 and e.payload_offset - e.file_offset == 2
    changed = bytearray(raw[: e.file_offset + 1] + b"\x98\0" + raw[e.payload_offset :])
    struct.pack_into("<I", changed, 18, len(changed) - 22)
    with pytest.raises((ValueError, Suno2FLPError)):
        verify_audio_preview(bytes(changed), profile, plan)


def test_channel_blocks_cannot_move_after_global_suffix():
    profile, _, plan = case()
    raw = encode_audio_preview(profile, plan)
    inv = scan_template_inventory(raw)
    first = next(j for j, e in enumerate(inv.events) if e.event_id == 64)
    count = 3 * len(profile.synth) + 9 * len(profile.sample)
    sequence = [
        *inv.events[:first],
        *inv.events[first + count :],
        *inv.events[first : first + count],
    ]
    body = b"".join(raw[e.file_offset : e.payload_offset + e.payload_size] for e in sequence)
    reordered = raw[:18] + struct.pack("<I", len(body)) + body
    with pytest.raises((ValueError, Suno2FLPError)):
        verify_audio_preview(reordered, profile, plan)
