"""Narrow field observations from independent exact-build host experiments.

These predicates do not certify a file, decode every flag bit, or authorize crop edits.
Legacy inventory float projections and full raw records remain unchanged.
"""

import struct
from typing import Literal, NamedTuple

from suno2flp.core.template_inventory import TemplateClipRecord, TemplateNoteRecord
from suno2flp.core.template_profiles import FL26_READ_PROFILE


def note_attribute_form(
    note: TemplateNoteRecord, profile_id: str | None
) -> Literal["ordinary", "slide"] | None:
    """Match the whole observed positive-note attribute combination, not just 0x4000."""
    raw = bytes.fromhex(note.raw_hex)
    if (
        profile_id != FL26_READ_PROFILE.identifier
        or note.length_ticks <= 0
        or note.group
        or raw[13:21] != bytes.fromhex("0000007800400040")
        or raw[22:24] != b"\x80\x80"
    ):
        return None
    if note.flags == 0x4000:
        return "ordinary"
    if note.flags == 0x4008:
        return "slide"
    return None


class PatternCropObservation(NamedTuple):
    form: Literal["default_sentinel", "explicit_ticks"]
    start_ticks: int | None
    end_ticks: int | None


def pattern_crop_observation(
    clip: TemplateClipRecord, profile_id: str | None
) -> PatternCropObservation | None:
    """Read observed Pattern endpoints in template ticks; never coerce sentinel bits to zero."""
    if (
        profile_id != FL26_READ_PROFILE.identifier
        or clip.record_size != 88
        or clip.kind != "pattern"
        or clip.group
        or clip.position_ticks < 0
        or clip.length_ticks <= 0
    ):
        return None
    start, end = struct.unpack_from("<ii", bytes.fromhex(clip.raw_hex), 24)
    if clip.flags == 0x8040 and (start, end) == (-1, -1):
        return PatternCropObservation("default_sentinel", None, None)
    if clip.flags == 0x40 and 0 <= start < end and end - start == clip.length_ticks:
        return PatternCropObservation("explicit_ticks", start, end)
    return None
