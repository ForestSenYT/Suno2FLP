"""Deterministic maximum-cardinality bipartite matching on exact source times."""

import time
from bisect import bisect_left, bisect_right
from collections import defaultdict, deque
from collections.abc import Callable
from fractions import Fraction

from suno2flp.core.errors import OfflineError
from suno2flp.core.note_scoring import (
    MATCH_SECONDS,
    MAX_EDGES,
    MAX_NOTES,
    ExactRatio,
    NoteMatch,
    NoteScore,
    ScoredNote,
    time_fraction,
)
from suno2flp.core.performance import RationalTime


def score_notes(
    candidate: list[ScoredNote],
    reference: list[ScoredNote] | None,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> NoteScore:
    deadline = time.monotonic() + MATCH_SECONDS

    def check() -> None:
        if should_cancel and should_cancel():
            raise OfflineError("note_score_cancelled", "Note scoring cancelled")
        if time.monotonic() > deadline:
            raise OfflineError("note_score_timeout", "Note matching exceeded its time budget")

    for notes in (candidate, reference or []):
        if len(notes) > MAX_NOTES:
            raise OfflineError("note_score_limit", "Too many notes for the fixed profile")
    # A model's nested fields may have changed since construction. Revalidate into
    # owned snapshots before invoking caller callbacks or using any coordinates.
    candidate = [ScoredNote.model_validate(note.model_dump()) for note in candidate]
    reference = (
        [ScoredNote.model_validate(note.model_dump()) for note in reference]
        if reference is not None
        else None
    )
    check()
    for notes in (candidate, reference or []):
        if len({note.id for note in notes}) != len(notes):
            raise ValueError("Note IDs must be unique within each annotation")
    refs = sorted(reference or [], key=lambda note: note.id)
    candidates = sorted(candidate, key=lambda note: note.id)
    if not refs:
        return NoteScore(
            status="reference_unavailable" if reference is None else "no_reference_notes",
            candidate_count=len(candidates),
            reference_count=None if reference is None else 0,
            true_positives=0,
            matches=[],
            unmatched_reference_ids=[],
            unmatched_candidate_ids=[note.id for note in candidates],
        )
    buckets: dict[int, list[tuple[Fraction, int]]] = defaultdict(list)
    starts = [time_fraction(note.onset_microseconds) for note in candidates]
    ends = [time_fraction(note.offset_microseconds) for note in candidates]
    for index, note in enumerate(candidates):
        buckets[note.pitch].append((starts[index], index))
    for bucket in buckets.values():
        bucket.sort()
    edges: list[list[int]] = []
    total = 0
    for note in refs:
        check()
        start, end = time_fraction(note.onset_microseconds), time_fraction(note.offset_microseconds)
        tolerance = max(Fraction(50_000), (end - start) / 5)
        bucket = buckets[note.pitch]
        low = bisect_left(bucket, (start - 50_000, -1))
        high = bisect_right(bucket, (start + 50_000, len(candidates)))
        eligible = []
        for _, index in bucket[low:high]:
            if abs(ends[index] - end) <= tolerance:
                eligible.append(index)
                total += 1
                if total > MAX_EDGES:
                    raise OfflineError("note_score_limit", "Eligible edge budget exceeded")
        edges.append(sorted(eligible))

    # Incremental augmenting paths produce maximum cardinality, never reuse a note.
    # Iteration avoids recursion failure on long chains of overlapping notes.
    owner: dict[int, int] = {}
    assigned: dict[int, int] = {}
    for root in range(len(refs)):
        check()
        queue = deque([root])
        parent: dict[int, int] = {}
        seen = {root}
        free: int | None = None
        while queue and free is None:
            check()
            current = queue.popleft()
            for index in edges[current]:
                if index in parent:
                    continue
                parent[index] = current
                if index not in owner:
                    free = index
                    break
                next_ref = owner[index]
                if next_ref not in seen:
                    seen.add(next_ref)
                    queue.append(next_ref)
        while free is not None:
            ref_index = parent[free]
            previous = assigned.get(ref_index)
            owner[free] = ref_index
            assigned[ref_index] = free
            free = previous
    check()
    matches = [
        NoteMatch(
            reference_id=refs[r].id,
            candidate_id=candidates[c].id,
            onset_error_microseconds=RationalTime.exact(
                abs(time_fraction(refs[r].onset_microseconds) - starts[c])
            ),
            offset_error_microseconds=RationalTime.exact(
                abs(time_fraction(refs[r].offset_microseconds) - ends[c])
            ),
        )
        for r, c in sorted(assigned.items())
    ]
    count = len(matches)
    return NoteScore(
        status="measured",
        candidate_count=len(candidates),
        reference_count=len(refs),
        true_positives=count,
        precision=ExactRatio.exact(Fraction(count, len(candidates) or 1)),
        recall=ExactRatio.exact(Fraction(count, len(refs))),
        f1=ExactRatio.exact(Fraction(2 * count, len(refs) + len(candidates))),
        matches=matches,
        unmatched_reference_ids=[note.id for i, note in enumerate(refs) if i not in assigned],
        unmatched_candidate_ids=[note.id for i, note in enumerate(candidates) if i not in owner],
    )
