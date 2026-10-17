"""Original onset clusters; exhaustive oracle independent of the greedy matcher."""

import itertools
from fractions import Fraction

import pytest

from suno2flp.core.drum_scoring import DRUM_CLASSES, DrumScore, ScoredDrum
from suno2flp.core.errors import OfflineError
from suno2flp.core.note_scoring import time_fraction
from suno2flp.core.performance import RationalTime
from suno2flp.validator.drum_matching import score_drums


def drum(id, us, label="KD"):
    return ScoredDrum(id=id, label=label, microseconds=RationalTime.exact(Fraction(us)))


def test_exact_inclusive_boundary_and_wrong_class():
    refs = [drum("a", 0), drum("b", 200_000), drum("c", 400_000, "SD")]
    cs = [drum("x", 50_000), drum("y", Fraction(250_000) + Fraction(1, 3)), drum("z", 400_000)]
    result = score_drums(cs, refs)
    assert result.true_positives == 1
    assert result.f1.numerator == 1 and result.f1.denominator == 3
    assert [(m.reference_id, m.candidate_id) for m in result.matches] == [("a", "x")]
    assert time_fraction(result.matches[0].error_microseconds) == 50_000
    assert result.unmatched_candidate_ids == ["y", "z"]
    assert result.unmatched_reference_ids == ["b", "c"]


def test_all_classes_and_stable_ties_preserve_original_events():
    refs = [drum(f"r{i}", 123, label) for i, label in enumerate(DRUM_CLASSES)]
    cs = [drum(f"c{i}", 123, label) for i, label in enumerate(DRUM_CLASSES)]
    before = [e.model_dump() for e in refs + cs]
    a = score_drums(cs, refs)
    assert a.true_positives == 9 and a.f1.numerator == a.f1.denominator == 1
    assert a == score_drums(list(reversed(cs)), list(reversed(refs)))
    assert before == [e.model_dump() for e in refs + cs]
    ties = score_drums([drum("z", 0), drum("a", 0)], [drum("r", 0)])
    assert ties.matches[0].candidate_id == "a"
    assert ties.unmatched_candidate_ids == ["z"]


def oracle(cs, rs):
    if not rs:
        return 0
    return max(
        oracle(cs, rs[1:]),
        max(
            (
                1 + oracle(cs[:i] + cs[i + 1 :], rs[1:])
                for i, c in enumerate(cs)
                if abs(c - rs[0]) <= 50_000
            ),
            default=0,
        ),
    )


def test_maximum_cardinality_against_exhaustive_oracle():
    choices = [0, 40_000, 80_000, 120_000]
    for ctimes in itertools.combinations_with_replacement(choices, 3):
        for rtimes in itertools.combinations_with_replacement(choices, 3):
            cs = [drum(f"c{i}", t) for i, t in enumerate(ctimes)]
            rs = [drum(f"r{i}", t) for i, t in enumerate(rtimes)]
            assert score_drums(cs, rs).true_positives == oracle(list(ctimes), list(rtimes))


@pytest.mark.parametrize(
    "refs,status", [(None, "reference_unavailable"), ([], "no_reference_events")]
)
def test_no_truth_is_never_a_quality_score(refs, status):
    result = score_drums([drum("c", 0)], refs)
    assert result.status == status and result.f1 is None
    assert result.precision is None and result.recall is None
    assert result.model_qualification == "not_assessed"
    assert result.writer_eligibility == "blocked"
    assert result.execution_allowed is False


def test_empty_candidate_with_truth_scores_zero():
    result = score_drums([], [drum("r", 0)])
    assert result.status == "measured" and result.f1.numerator == 0


def test_duplicates_mutated_models_limits_and_cancellation():
    with pytest.raises(ValueError, match="unique"):
        score_drums([drum("a", 0), drum("a", 1)], [])
    bad = drum("bad", 0)
    bad.microseconds.__dict__["denominator"] = 0
    with pytest.raises(ValueError):
        score_drums([bad], None)
    with pytest.raises(ValueError, match="budget"):
        score_drums([drum("c", 0)] * 20_001, [])
    with pytest.raises(OfflineError, match="cancel"):
        score_drums([], [], should_cancel=lambda: True)


def test_caller_callback_cannot_change_owned_coordinates():
    cs, rs = [drum("c", 0)], [drum("r", 0)]

    def mutate():
        cs[0].microseconds.numerator = 1_000_000
        return False

    assert score_drums(cs, rs, should_cancel=mutate).true_positives == 1


def test_forged_metrics_and_out_of_window_matches_rejected():
    result = score_drums([drum("c", 0)], [drum("r", 0)])
    data = result.model_dump()
    data["f1"] = {"numerator": 0, "denominator": 1}
    with pytest.raises(ValueError):
        DrumScore.model_validate(data)
    data = result.model_dump()
    data["matches"][0]["error_microseconds"]["numerator"] = 50_001
    with pytest.raises(ValueError):
        DrumScore.model_validate(data)


@pytest.mark.parametrize("label", ["kick", "36", "TT_unknown"])
def test_no_implicit_class_aliases(label):
    with pytest.raises(ValueError):
        drum("c", 0, label)
