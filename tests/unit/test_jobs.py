"""Job snapshots cannot invent stage completion or lose transition evidence."""

import copy

import pytest

from suno2flp.core.offline_files import capture_stream_input


STAGES = [
    "input",
    "decode",
    "separate",
    "analyze",
    "transcribe",
    "arrange",
    "route",
    "write",
    "host_verify",
    "quality",
    "publish",
]


@pytest.fixture
def document(tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"source identity fixture")
    identity = capture_stream_input(source)
    return {
        "job_id": "job-one",
        "source": identity.model_dump(mode="json"),
        "output_directory": str(tmp_path / "new-output"),
        "status": "queued",
        "stages": [
            {"stage": stage, "status": "queued", "progress": 0, "outputs": []} for stage in STAGES
        ],
        "history": [{"sequence": 0, "kind": "created"}],
    }


def parse(document):
    from suno2flp.core.jobs import ConversionJob

    return ConversionJob.model_validate(document)


def test_valid_job_keeps_source_and_pending_stages_without_writer_permission(document):
    job = parse(document)
    assert job.source.model_dump(mode="json") == document["source"]
    assert [stage.stage for stage in job.stages] == STAGES
    assert job.status == "queued"
    assert job.execution_allowed is False and job.writer_eligibility == "blocked"
    assert job.host_compatibility == "unverified"
    assert job.history[0].kind == "created"


@pytest.mark.parametrize("change", ["reorder", "duplicate", "omit"])
def test_snapshot_rejects_invalid_stage_coverage(document, change):
    if change == "reorder":
        document["stages"][0], document["stages"][1] = document["stages"][1], document["stages"][0]
    elif change == "duplicate":
        document["stages"][1] = copy.deepcopy(document["stages"][0])
    else:
        document["stages"].pop()
    with pytest.raises(ValueError):
        parse(document)


@pytest.mark.parametrize("progress", [-1, 101, 1.5, True, "20", float("nan"), float("inf")])
def test_progress_is_a_bounded_strict_integer(document, progress):
    document["stages"][0]["progress"] = progress
    with pytest.raises(ValueError):
        parse(document)


def test_stage_cannot_be_successful_without_evidence_or_history(document):
    document["stages"][0].update(status="succeeded", progress=100)
    with pytest.raises(ValueError):
        parse(document)


@pytest.mark.parametrize("status", ["running", "succeeded", "failed", "blocked", "cancelled"])
def test_global_status_must_follow_recorded_events(document, status):
    document["status"] = status
    with pytest.raises(ValueError):
        parse(document)


def test_reordered_or_missing_history_is_rejected(document):
    for history in (
        [],
        [{"sequence": 1, "kind": "created"}],
        [{"sequence": 0, "kind": "created"}, {"sequence": 0, "kind": "created"}],
    ):
        document["history"] = history
        with pytest.raises(ValueError):
            parse(document)


def test_input_snapshot_is_independent_of_caller_mutations(document):
    job = parse(document)
    document["stages"][0]["progress"] = 99
    document["source"]["sha256"] = "0" * 64
    assert job.stages[0].progress == 0
    assert job.source.sha256 != "0" * 64


def test_job_paths_are_absolute_and_job_identifier_is_portable(document):
    for field, value in (("output_directory", "relative"), ("job_id", "../unsafe")):
        altered = copy.deepcopy(document)
        altered[field] = value
        with pytest.raises(ValueError):
            parse(altered)


def test_serialized_final_success_never_substitutes_for_publication_proof(document):
    document["status"] = "succeeded"
    document["execution_allowed"] = True
    document["writer_eligibility"] = "ready"
    with pytest.raises(ValueError):
        parse(document)
