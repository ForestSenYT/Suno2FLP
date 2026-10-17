"""Exact observed component pin; structural helpers have no file/write authority."""

import hashlib
from dataclasses import dataclass

from suno2flp.core.template_inventory import TemplateEventEvidence, TemplateInventory
from suno2flp.integrations.template_inventory import scan_template_inventory

BASE_SHA256 = "f2613d7c0b3e424cc39bfacc87cf49e5366aac25b44fbb071e983d268dfdbcc8"
SAMPLER_SHA256 = "3a25d7238c2e35d5268759785acc06749f2b7c43bcf33ccfa0cbfd82cdc793f6"


@dataclass(frozen=True)
class AudioComponents:
    base: bytes
    sampler: bytes
    inventory: TemplateInventory
    synth: tuple[TemplateEventEvidence, ...]
    sample: tuple[TemplateEventEvidence, ...]


def record(raw: bytes, event: TemplateEventEvidence) -> bytes:
    return raw[event.file_offset : event.payload_offset + event.payload_size]


def payload(raw: bytes, event: TemplateEventEvidence) -> bytes:
    return raw[event.payload_offset : event.payload_offset + event.payload_size]


def components(base: bytes, sampler: bytes) -> AudioComponents:
    """Pure structural extraction for original fixtures; file exports additionally pin bytes."""
    bi, si = scan_template_inventory(base), scan_template_inventory(sampler)
    if any(i.fl_studio_version != "26.1.7.5654" or i.ppq != 96 for i in (bi, si)):
        raise ValueError("Use the exact assessed FL26 component clock")
    starts = [j for j, e in enumerate(bi.events) if e.event_id == 64]
    selected = [j for j, e in enumerate(si.events) if e.event_id == 64]
    if len(starts) != 1 or len(selected) != 2 or bi.channel_count != 1 or si.channel_count != 2:
        raise ValueError("Component channel scopes changed")
    a = starts[0]
    b = next(
        (j for j in range(a + 1, len(bi.events)) if bi.events[j].event_id == 99), len(bi.events)
    )
    c = selected[1]
    d = next(
        (j for j in range(c + 1, len(si.events)) if si.events[j].event_id == 99), len(si.events)
    )
    synth, sample = tuple(bi.events[a:b]), tuple(si.events[c:d])
    for raw, block, kind in ((base, synth, b"\2"), (sampler, sample, b"\0")):
        for identifier in (21, 0, 132, 219, 203):
            if sum(e.event_id == identifier for e in block) != 1:
                raise ValueError("Component scalar scope is incomplete or duplicated")
        if payload(raw, next(e for e in block if e.event_id == 21)) != kind:
            raise ValueError("Wrong component channel type")
    if (
        any(e.event_id in (201, 212, 213) for e in sample)
        or sum(e.event_id == 196 for e in sample) != 1
    ):
        raise ValueError("Built-in sampler must not inherit plugin wrapper records")
    if len(bi.notes) < 1 or len(bi.clips) != 1 or len(bi.automation) > 0:
        raise ValueError("Use the ordinary note/one-clip reference without automation")
    if (
        sum(e.event_id == 224 for e in bi.events) != 1
        or sum(e.event_id == 233 for e in bi.events) != 1
    ):
        raise ValueError("Ambiguous note/playlist scope")
    clip = bi.clips[0]
    if (
        clip.record_size != 88
        or clip.position_ticks != 0
        or clip.track != 0
        or clip.flags != 64
        or clip.muted
        or clip.group != 0
    ):
        raise ValueError("Use the observed ordinary non-cut clip profile")
    return AudioComponents(base, sampler, bi, synth, sample)


def pinned_components(base: bytes, sampler: bytes) -> AudioComponents:
    if (hashlib.sha256(base).hexdigest(), hashlib.sha256(sampler).hexdigest()) != (
        BASE_SHA256,
        SAMPLER_SHA256,
    ):
        raise ValueError("Use the pinned, separately observed reference components")
    return components(base, sampler)
