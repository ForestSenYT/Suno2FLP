"""Exact-build read profiles; these declare no writer or playback capability."""

from typing import Literal, NamedTuple


class TemplateReadProfile(NamedTuple):
    identifier: Literal["fl25-25.1.2.4896-read-v1", "fl26-26.1.7.5654-read-v1"]
    version: str
    playlist_record_size: int
    event_172_size: int


FL25_READ_PROFILE = TemplateReadProfile("fl25-25.1.2.4896-read-v1", "25.1.2.4896", 80, 4)
FL26_READ_PROFILE = TemplateReadProfile("fl26-26.1.7.5654-read-v1", "26.1.7.5654", 88, 3)


def read_profile(version: str | None) -> TemplateReadProfile | None:
    for profile in (FL25_READ_PROFILE, FL26_READ_PROFILE):
        if version == profile.version:
            return profile
    return None
