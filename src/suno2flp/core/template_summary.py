"""Pure selected-family byte summaries; never substitutes a backend or DAW result."""

from collections import Counter
from fractions import Fraction
from typing import Literal, cast

from pydantic import JsonValue

from suno2flp.core.backend_models import (
    BackendSummaryMismatch,
    Music2DawSummary,
    TemplateLocalSummary,
)
from suno2flp.core.template_inventory import TemplateInventory
from suno2flp.core.template_profiles import read_profile

SummaryStatus = Literal["unchecked", "consistent", "inconsistent"]


def summarize_inventory(inventory: TemplateInventory) -> TemplateLocalSummary | None:
    profile = read_profile(inventory.fl_studio_version)
    if profile is None:
        return None
    tempo_events = [e for e in inventory.events if e.event_id in {66, 156}]
    tempo = None
    if tempo_events:
        last = tempo_events[-1]
        if last.scalar_hex is not None:
            tempo = int.from_bytes(bytes.fromhex(last.scalar_hex), "little")
            if last.event_id == 66:
                tempo *= 1000
    note_events = [e for e in inventory.events if e.event_id == 224]
    note_counts = Counter(note.pattern_id for note in inventory.notes)
    declared_patterns = [
        e.pattern_id for e in inventory.events if e.event_id == 65 and e.pattern_id is not None
    ]
    patterns = {
        index: note_counts[index] for index in range(max(declared_patterns, default=-1) + 1)
    }
    notes_complete = all(e.pattern_id is not None and e.payload_size % 24 == 0 for e in note_events)
    notes_complete = (
        notes_complete and sum(e.payload_size for e in note_events) == len(inventory.notes) * 24
    )
    playlist_events = [e for e in inventory.events if e.event_id == 233]
    clips_complete = all(
        e.payload_size > 0 and e.payload_size % profile.playlist_record_size == 0
        for e in playlist_events
    )
    clips_complete = (
        clips_complete
        and sum(e.payload_size for e in playlist_events)
        == len(inventory.clips) * profile.playlist_record_size
    )
    return TemplateLocalSummary(
        profile_id=profile.identifier,
        fl_studio_version=profile.version,
        ppq=inventory.ppq,
        channel_count=inventory.channel_count,
        tempo_millibpm=tempo,
        tempo_event_indices=[e.event_index for e in tempo_events],
        pattern_note_counts=patterns if notes_complete else None,
        pattern_event_indices=[e.event_index for e in inventory.events if e.event_id in {65, 224}],
        playlist_item_count=len(inventory.clips) if clips_complete else None,
        playlist_event_indices=[e.event_index for e in playlist_events],
    )


def compare_backend_summary(
    inventory: TemplateInventory,
    project: Music2DawSummary,
) -> tuple[TemplateLocalSummary | None, SummaryStatus, list[BackendSummaryMismatch]]:
    local = summarize_inventory(inventory)
    if local is None:
        return None, "unchecked", []
    mismatches = []

    def compare(field: str, backend: JsonValue, observed: JsonValue, events: list[int]) -> None:
        if backend != observed:
            mismatches.append(
                BackendSummaryMismatch(
                    field=field, backend_value=backend, local_value=observed, event_indices=events
                )
            )

    compare(
        "fl_studio_version",
        project.fl_studio_version,
        local.fl_studio_version,
        [e.event_index for e in inventory.events if e.event_id == 199],
    )
    compare("ppq", project.ppq, local.ppq, [])
    compare("channel_count", len(project.channels), local.channel_count, [])
    if local.tempo_millibpm is not None:
        if Fraction(str(project.tempo)) * 1000 != local.tempo_millibpm:
            mismatches.append(
                BackendSummaryMismatch(
                    field="tempo",
                    backend_value=project.tempo,
                    local_value=local.tempo_millibpm / 1000,
                    event_indices=local.tempo_event_indices,
                )
            )
    if local.pattern_note_counts is not None:
        backend_patterns: dict[str, JsonValue] = {
            str(cast(int, p["id"])): p["noteCount"] for p in project.patterns
        }
        local_patterns: dict[str, JsonValue] = {
            str(index): count for index, count in local.pattern_note_counts.items()
        }
        compare("patterns", backend_patterns, local_patterns, local.pattern_event_indices)
    if local.playlist_item_count is not None:
        compare(
            "playlist_item_count",
            project.playlist_item_count,
            local.playlist_item_count,
            local.playlist_event_indices,
        )
    complete = (
        local.tempo_millibpm is not None
        and local.pattern_note_counts is not None
        and local.playlist_item_count is not None
    )
    return (
        local,
        "inconsistent" if mismatches else "consistent" if complete else "unchecked",
        mismatches,
    )
