"""Job snapshots cannot invent stage completion or lose transition evidence."""

import copy
from pathlib import Path

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
        "history": [{"sequence": 0, "kind": "created", "source": identity.model_dump(mode="json")}],
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
    assert job.history[0].source == job.source


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


def service():
    from suno2flp.pipeline import jobs

    return jobs


@pytest.fixture
def queued(document):
    job = parse(document)
    job.output_directory.mkdir()
    return job


def output(job, name):
    path = job.output_directory / f"{name}.json"
    path.write_text('{"evidence":"synthetic contract fixture"}', encoding="utf-8")
    return capture_stream_input(path)


def completed_input(job):
    running = service().start_stage(job, "input")
    return service().finish_stage(running, "input", [output(job, "input")])


def test_new_job_does_not_create_or_modify_files(document):
    source = parse(document).source
    before = source.path.read_bytes()
    job = service().new_job("job-one", source, Path(document["output_directory"]))
    assert not job.output_directory.exists()
    assert source.path.read_bytes() == before
    assert job.source == source and job.source is not source
    assert job.history[0].source == source and job.history[0].source is not job.source


def test_ordered_stage_transitions_keep_input_job_immutable(queued):
    before = queued.model_dump()
    running = service().start_stage(queued, "input")
    progressed = service().report_progress(running, "input", 42)
    evidence = output(queued, "input")
    finished = service().finish_stage(progressed, "input", [evidence])
    assert queued.model_dump() == before
    assert running.stages[0].progress == 0
    assert finished.status == "queued"
    assert finished.stages[0].status == "succeeded" and finished.stages[0].progress == 100
    assert finished.stages[0].outputs == [evidence]
    assert finished.stages[1].status == "queued"
    assert [e.kind for e in finished.history] == ["created", "started", "progress", "finished"]
    assert [e.sequence for e in finished.history] == [0, 1, 2, 3]
    assert finished.execution_allowed is False
    evidence.sha256 = "0" * 64
    assert finished.stages[0].outputs[0].sha256 != "0" * 64


def test_start_requires_next_stage_and_no_active_worker(queued):
    with pytest.raises(ValueError):
        service().start_stage(queued, "decode")
    running = service().start_stage(queued, "input")
    with pytest.raises(ValueError):
        service().start_stage(running, "input")
    finished = completed_input(queued)
    with pytest.raises(ValueError):
        service().start_stage(finished, "input")


@pytest.mark.parametrize("value", [-1, 100, True, "20", 20.5, float("nan")])
def test_running_progress_cannot_claim_completion_or_coerce_values(queued, value):
    running = service().start_stage(queued, "input")
    with pytest.raises(ValueError):
        service().report_progress(running, "input", value)


def test_progress_cannot_move_backwards_or_target_other_stage(queued):
    running = service().report_progress(service().start_stage(queued, "input"), "input", 80)
    for stage, progress in (("input", 79), ("decode", 90)):
        with pytest.raises(ValueError):
            service().report_progress(running, stage, progress)


def test_finish_needs_running_stage_and_current_unique_contained_evidence(queued):
    evidence = output(queued, "input")
    with pytest.raises(ValueError):
        service().finish_stage(queued, "input", [evidence])
    running = service().start_stage(queued, "input")
    for evidence_list in ([], [evidence, evidence], [queued.source]):
        with pytest.raises(ValueError):
            service().finish_stage(running, "input", evidence_list)
    finished = service().finish_stage(running, "input", [evidence])
    decode = service().start_stage(finished, "decode")
    with pytest.raises(ValueError):
        service().finish_stage(decode, "decode", [evidence])


@pytest.mark.parametrize("status", ["blocked", "failed", "cancelled"])
def test_stop_and_resume_preserve_completed_evidence_and_attempt_history(queued, status):
    completed = completed_input(queued)
    running = service().report_progress(service().start_stage(completed, "decode"), "decode", 30)
    stopped = service().stop_job(running, status, "synthetic_stop")
    resumed = service().resume_job(stopped)
    assert running.status == "running" and running.stages[1].progress == 30
    assert stopped.status == status and stopped.stages[1].status == status
    assert stopped.history[-1].code == "synthetic_stop"
    assert resumed.status == "queued" and resumed.stages[1].status == "queued"
    assert resumed.stages[1].progress == 0
    assert resumed.stages[0] == completed.stages[0]
    assert resumed.history[:-1] == stopped.history
    assert resumed.history[-1].kind == "resumed"


def test_cancel_before_start_is_recoverable_and_active_job_cannot_resume(queued):
    stopped = service().stop_job(queued, "cancelled", "user_cancelled")
    assert stopped.stages == queued.stages
    assert service().resume_job(stopped).status == "queued"
    with pytest.raises(ValueError):
        service().resume_job(queued)


@pytest.mark.parametrize("which", ["source", "output"])
def test_resume_checks_current_source_and_completed_output_identity(queued, which):
    from suno2flp.core.errors import OfflineError

    completed = completed_input(queued)
    stopped = service().stop_job(completed, "blocked", "backend_missing")
    target = queued.source.path if which == "source" else completed.stages[0].outputs[0].path
    target.write_bytes(b"changed")
    with pytest.raises(OfflineError):
        service().resume_job(stopped)


def test_file_identity_changes_are_checked_at_stage_boundaries_but_cancellation_still_works(queued):
    from suno2flp.core.errors import OfflineError

    running = service().start_stage(queued, "input")
    evidence = output(queued, "input")
    queued.source.path.write_bytes(b"changed")
    with pytest.raises(OfflineError):
        service().start_stage(queued, "input")
    with pytest.raises(OfflineError):
        service().finish_stage(running, "input", [evidence])
    assert service().stop_job(running, "cancelled", "user_cancelled").status == "cancelled"


def test_mutated_snapshot_or_history_is_not_consumed_as_valid_progress(queued):
    queued.stages[0].progress = 20
    with pytest.raises(ValueError):
        service().start_stage(queued, "input")


def test_final_publication_cannot_be_completed_by_foundation_helpers(queued):
    job = queued
    for stage in STAGES[:-1]:
        job = service().finish_stage(service().start_stage(job, stage), stage, [output(job, stage)])
    publishing = service().start_stage(job, "publish")
    with pytest.raises(ValueError, match="publication"):
        service().finish_stage(publishing, "publish", [output(job, "publish")])
    assert publishing.status == "running" and publishing.execution_allowed is False


def test_new_job_refuses_existing_or_source_containing_output_directory(document):
    source = parse(document).source
    with pytest.raises(ValueError):
        service().new_job("job-one", source, source.path.parent)


def test_loaded_snapshot_cannot_reassign_output_to_original_input_tree(document):
    document["output_directory"] = str(Path(document["source"]["path"]).parent)
    with pytest.raises(ValueError):
        parse(document)


@pytest.mark.parametrize("replacement", ["changed_content", "different_file"])
def test_replacing_source_identity_cannot_reuse_completed_stages(queued, replacement):
    stopped = service().stop_job(completed_input(queued), "blocked", "backend_missing")
    if replacement == "changed_content":
        path = stopped.source.path
    else:
        path = stopped.source.path.with_name("other-source.wav")
    path.write_bytes(b"replacement source")
    changed = capture_stream_input(path)
    forged = stopped.model_copy(deep=True, update={"source": changed})
    with pytest.raises(ValueError):
        service().resume_job(forged)
