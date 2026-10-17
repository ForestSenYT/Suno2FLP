"""Original candidate encoder with explicit occurrence routing; no host actions."""

import struct

from suno2flp.arrangement.midi_preview import project_estimated_midi
from suno2flp.core.audio_flp import (
    DRUM_PREVIEW_KEYS,
    PITCH_CHANNELS,
    AudioPreviewNote,
    AudioPreviewPlan,
)
from suno2flp.core.estimated_midi import EstimatedMidiScore
from suno2flp.core.evidence import snapshot_sha256
from suno2flp.flp_builder.audio_profile import AudioComponents, payload, record


def audio_preview_plan(score: EstimatedMidiScore) -> AudioPreviewPlan:
    if score != project_estimated_midi(score.arrangement):
        raise ValueError("Use the complete unchanged estimated MIDI projection")
    notes = []
    for part_index, part in enumerate(score.parts):
        for index, n in enumerate(part.notes):
            drum = part.stem == "drums"
            notes.append(
                AudioPreviewNote(
                    source_part=part_index,
                    source_occurrence=index,
                    stem=part.stem,
                    source_pitch=n.pitch,
                    channel=3 + DRUM_PREVIEW_KEYS.index(n.pitch)
                    if drum
                    else PITCH_CHANNELS[part.stem],
                    pitch=60 if drum else n.pitch,
                    start_tick=n.start.tick,
                    end_tick=n.end.tick,
                )
            )
    end = ((score.end_tick + 3840 + 3839) // 3840) * 3840
    return AudioPreviewPlan(source_score_sha256=snapshot_sha256(score), notes=notes, end_tick=end)


def sample_reference(channel: int) -> str:
    return f"audio\\drum-{DRUM_PREVIEW_KEYS[channel - 3]}.wav"


def _event(identifier: int, value: bytes) -> bytes:
    if identifier < 192:
        return bytes([identifier]) + value
    size = len(value)
    out = bytearray([identifier])
    while size >= 128:
        out.append((size & 127) | 128)
        size >>= 7
    return bytes(out) + bytes([size]) + value


def encode_audio_preview(profile: AudioComponents, plan: AudioPreviewPlan) -> bytes:
    plan = AudioPreviewPlan.model_validate(plan.model_dump())
    blocks = bytearray()
    for channel in range(12):
        raw, block = (
            (profile.base, profile.synth) if channel < 3 else (profile.sampler, profile.sample)
        )
        for e in block:
            value = payload(raw, e)
            new = value
            if e.event_id == 64:
                new = struct.pack("<H", channel)
            elif e.event_id == 0:
                new = b"\1"
            elif e.event_id == 219:
                changed = bytearray(value)
                struct.pack_into("<I", changed, 4, plan.channel_gain)
                new = bytes(changed)
            elif e.event_id == 203:
                label = (
                    ("vocals", "bass", "other")[channel]
                    if channel < 3
                    else f"drum-{DRUM_PREVIEW_KEYS[channel - 3]}"
                )
                new = f"Suno2FLP {label}\0".encode("utf-16-le")
            elif e.event_id == 196:
                new = (sample_reference(channel) + "\0").encode("utf-16-le")
            blocks.extend(record(raw, e) if new == value else _event(e.event_id, new))
    original = profile.inventory
    notes = bytearray()
    for n in plan.notes:
        data = bytearray.fromhex(original.notes[0].raw_hex)
        struct.pack_into("<I", data, 0, n.start_tick)
        struct.pack_into("<H", data, 6, n.channel)
        struct.pack_into("<I", data, 8, n.end_tick - n.start_tick)
        struct.pack_into("<H", data, 12, n.pitch)
        data[21] = n.velocity
        notes.extend(data)
    clip = bytearray.fromhex(original.clips[0].raw_hex)
    struct.pack_into("<I", clip, 8, plan.end_tick)
    struct.pack_into("<I", clip, 24, 0)
    struct.pack_into("<I", clip, 28, plan.end_tick)
    channel_events = {e.event_index for e in profile.synth}
    out = bytearray()
    for e in original.events:
        if e.event_index == profile.synth[0].event_index:
            out.extend(blocks)
        if e.event_index in channel_events:
            continue
        replacement = (
            bytes(notes) if e.event_id == 224 else bytes(clip) if e.event_id == 233 else None
        )
        out.extend(
            record(profile.base, e) if replacement is None else _event(e.event_id, replacement)
        )
    header = bytearray(profile.base[:18])
    struct.pack_into("<H", header, 10, 12)
    struct.pack_into("<H", header, 12, 960)
    return bytes(header) + struct.pack("<I", len(out)) + bytes(out)
