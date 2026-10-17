"""Linear matching after sorting; no offsets, velocity or inferred GM routing."""

from collections.abc import Callable
from fractions import Fraction

from suno2flp.core.drum_scoring import (
    DRUM_CLASSES,
    MAX_DRUMS,
    ONSET_TOLERANCE_US,
    DrumMatch,
    DrumScore,
    ScoredDrum,
)
from suno2flp.core.errors import OfflineError
from suno2flp.core.note_scoring import ExactRatio, time_fraction
from suno2flp.core.performance import RationalTime


def score_drums(
    candidate: list[ScoredDrum],
    reference: list[ScoredDrum] | None,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> DrumScore:
    if len(candidate) > MAX_DRUMS or len(reference or []) > MAX_DRUMS:
        raise ValueError("Drum annotation exceeds the fixed event budget")
    # Validate and own all nested coordinates before invoking caller callbacks.
    cs = [ScoredDrum.model_validate(e.model_dump()) for e in candidate]
    rs = [ScoredDrum.model_validate(e.model_dump()) for e in reference or []]

    def check() -> None:
        if should_cancel is not None and should_cancel():
            raise OfflineError("drum_score_cancelled", "Drum scoring cancelled")

    check()
    for events in (cs, rs):
        if len({e.id for e in events}) != len(events):
            raise ValueError("Drum event IDs must be unique within each annotation")
    matches = []
    for label in DRUM_CLASSES:
        ctimes = sorted((time_fraction(e.microseconds), e.id) for e in cs if e.label == label)
        rtimes = sorted((time_fraction(e.microseconds), e.id) for e in rs if e.label == label)
        c, r = 0, 0
        while c < len(ctimes) and r < len(rtimes):
            check()
            ct, cid = ctimes[c]
            rt, rid = rtimes[r]
            if ct < rt - ONSET_TOLERANCE_US:
                c += 1
            elif rt < ct - ONSET_TOLERANCE_US:
                r += 1
            else:
                # Exchange argument: earliest feasible pair can be in a maximum
                # matching. Swapping crossed pairs preserves the common window.
                # This maximizes count, not minimum error among tied matchings.
                matches.append(
                    DrumMatch(
                        candidate_id=cid,
                        reference_id=rid,
                        label=label,
                        error_microseconds=RationalTime.exact(abs(ct - rt)),
                    )
                )
                c += 1
                r += 1
    check()
    matched_cs = {p.candidate_id for p in matches}
    matched_rs = {p.reference_id for p in matches}
    count = len(matches)
    return DrumScore(
        status="measured"
        if rs
        else ("reference_unavailable" if reference is None else "no_reference_events"),
        candidate_count=len(cs),
        reference_count=len(rs) if reference is not None else None,
        true_positives=count,
        matches=sorted(matches, key=lambda m: (m.reference_id, m.candidate_id)),
        unmatched_candidate_ids=sorted(e.id for e in cs if e.id not in matched_cs),
        unmatched_reference_ids=sorted(e.id for e in rs if e.id not in matched_rs),
        precision=ExactRatio.exact(Fraction(count, len(cs) or 1)) if rs else None,
        recall=ExactRatio.exact(Fraction(count, len(rs))) if rs else None,
        f1=ExactRatio.exact(Fraction(2 * count, len(rs) + len(cs))) if rs else None,
    )
