"""Exact label matching, maximum count then minimum global absolute error."""

import time
from collections.abc import Callable
from fractions import Fraction

from suno2flp.core.beat_scoring import (
    MATCH_WINDOW_US,
    MAX_BEATS,
    MAX_MATCH_CELLS,
    BeatMatch,
    BeatScore,
    ScoredBeat,
)
from suno2flp.core.errors import OfflineError
from suno2flp.core.note_scoring import ExactRatio, time_fraction
from suno2flp.core.performance import RationalTime


def score_beats(
    candidate: list[ScoredBeat],
    reference: list[ScoredBeat] | None,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> BeatScore:
    deadline = time.monotonic() + 60

    def check() -> None:
        if should_cancel is not None and should_cancel():
            raise OfflineError("beat_score_cancelled", "Beat scoring cancelled")
        if time.monotonic() > deadline:
            raise OfflineError("beat_score_timeout", "Beat matching exceeded60seconds")

    if len(candidate) > MAX_BEATS or (reference is not None and len(reference) > MAX_BEATS):
        raise ValueError("Beat annotation exceeds its event budget")
    # Own snapshots before any caller callback can mutate nested coordinates.
    candidates = [ScoredBeat.model_validate(b.model_dump()) for b in candidate]
    refs = [ScoredBeat.model_validate(b.model_dump()) for b in reference or []]
    check()
    for beats in (candidates, refs):
        if len({b.id for b in beats}) != len(beats):
            raise ValueError("Beat IDs must be unique within each annotation")
        if any(time_fraction(b.microseconds) > 601_000_000 for b in beats):
            raise ValueError("Beat annotation exceeds the supported source duration")
    pairs: list[tuple[ScoredBeat, ScoredBeat]] = []
    cells = 0
    for label in ("beat", "downbeat"):
        cs = sorted(
            (b for b in candidates if b.label == label),
            key=lambda b: (time_fraction(b.microseconds), b.id),
        )
        rs = sorted(
            (b for b in refs if b.label == label),
            key=lambda b: (time_fraction(b.microseconds), b.id),
        )
        cells += (len(rs) + 1) * (len(cs) + 1)
        if cells > MAX_MATCH_CELLS:
            raise ValueError("Beat matching exceeds the fixed cell budget")
        if not cs or not rs:
            continue
        # Absolute distance is Monge on sorted points: an optimal feasible matching
        # can be uncrossed without losing count or increasing cost. The fixed
        # symmetric distance window preserves feasibility after uncrossing.
        width = len(cs) + 1
        actions = bytearray((len(rs) + 1) * width)
        counts = [0] * width
        costs = [Fraction(0)] * width
        ctimes = [time_fraction(c.microseconds) for c in cs]
        for i, ref in enumerate(rs, 1):
            check()
            next_counts, next_costs = [0] * width, [Fraction(0)] * width
            rtime = time_fraction(ref.microseconds)
            for j, ctime in enumerate(ctimes, 1):
                if j % 128 == 0:
                    check()
                # Ties retain earlier candidates, then earlier references.
                count, cost, action = next_counts[j - 1], next_costs[j - 1], 1
                if counts[j] > count or (counts[j] == count and costs[j] < cost):
                    count, cost, action = counts[j], costs[j], 2
                error = abs(rtime - ctime)
                new_count, new_cost = counts[j - 1] + 1, costs[j - 1] + error
                if error <= MATCH_WINDOW_US and (
                    new_count > count or (new_count == count and new_cost < cost)
                ):
                    count, cost, action = new_count, new_cost, 3
                next_counts[j], next_costs[j] = count, cost
                actions[i * width + j] = action
            counts, costs = next_counts, next_costs
        i, j = len(rs), len(cs)
        while i and j:
            action = actions[i * width + j]
            if action == 3:
                pairs.append((cs[j - 1], rs[i - 1]))
                i, j = i - 1, j - 1
            elif action == 1:
                j -= 1
            else:
                i -= 1
    check()
    matches = [
        BeatMatch(
            candidate_id=c.id,
            reference_id=r.id,
            label=c.label,
            error_microseconds=RationalTime.exact(
                abs(time_fraction(c.microseconds) - time_fraction(r.microseconds))
            ),
        )
        for c, r in sorted(pairs, key=lambda p: (p[1].id, p[0].id))
    ]
    errors = sorted(time_fraction(m.error_microseconds) for m in matches)
    count = len(errors)
    median = ((errors[(count - 1) // 2] + errors[count // 2]) / 2) if count else None
    p95 = errors[(95 * count + 99) // 100 - 1] if count else None
    candidate_ids, ref_ids = {c.id for c, _ in pairs}, {r.id for _, r in pairs}
    return BeatScore(
        status="measured"
        if refs
        else ("reference_unavailable" if reference is None else "no_reference_beats"),
        candidate_count=len(candidates),
        reference_count=len(refs) if reference is not None else None,
        matches=matches,
        unmatched_candidate_ids=sorted(b.id for b in candidates if b.id not in candidate_ids),
        unmatched_reference_ids=sorted(b.id for b in refs if b.id not in ref_ids),
        precision=ExactRatio.exact(Fraction(count, len(candidates)))
        if refs and candidates
        else None,
        recall=ExactRatio.exact(Fraction(count, len(refs))) if refs else None,
        median_error_microseconds=RationalTime.exact(median) if median is not None else None,
        p95_error_microseconds=RationalTime.exact(p95) if p95 is not None else None,
    )
