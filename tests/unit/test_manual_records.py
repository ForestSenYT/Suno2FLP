"""Original offline manual-record checks; never private project payloads."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from manual_record_fixtures import PROBES, REQUIRED, STAGES, json_file, make_record_set, save


@pytest.fixture
def record_set(tmp_path):
    return make_record_set(tmp_path)


def repin(record_set):
    root, path, manifest, records = record_set
    for entry, record in zip(manifest["records"], records, strict=True):
        entry["record"] = json_file(root, entry["record"]["path"], record)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def check(record_set):
    from suno2flp.validator.manual_records import check_manual_records

    root, path, *_ = record_set
    return check_manual_records(path, root)


def codes(report):
    return {item.code for item in report.diagnostics}


def complete_first(record_set):
    root, _, _, records = record_set
    record = records[0]
    record.update(operator="Synthetic operator", actual_version="26.1.7.5654")
    record["outputs"] = {
        "A": save(root / "a.flp", b"authored host A"),
        "B": save(root / "b.flp", b"authored host B"),
    }
    record["listening"] = {"A": "heard_as_recorded", "B": "heard_as_recorded"}
    for index, key in enumerate(STAGES):
        record["stages"][key] = {
            "status": "pass_observed",
            "performed_at": f"2026-10-16T04:{index:02d}:00-04:00",
            "details": "Synthetic observation, not real host evidence",
            "evidence": {
                slot: save(root / f"{key}-{slot}.txt", f"authored {key} {slot}".encode())
                for slot in REQUIRED[key]
            },
        }
    repin(record_set)


def test_intact_pending_is_not_host_success_and_never_launches_processes(record_set, monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: pytest.fail("process launched"))
    root = record_set[0]
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
    report = check(record_set)
    assert report.integrity_valid
    assert report.host_status == "pending_not_performed"
    assert report.stage_counts["pending_not_performed"] == 54
    assert report.writer_eligibility == "blocked" and report.execution_allowed is False
    assert report.host_compatibility == "unverified"
    assert len(report.records) == 6 and all(r.pending_stages == 9 for r in report.records)
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()} == before


@pytest.mark.parametrize("target", ["record", "form", "candidate", "protected", "provenance"])
def test_hash_changes_are_not_silently_rebased(record_set, target):
    root, _, manifest, _ = record_set
    ref = (
        manifest["records"][0][target]
        if target in {"record", "form", "candidate"}
        else manifest[target + "_files"][0]
    )
    (root / ref["path"]).write_bytes(b"changed")
    report = check(record_set)
    assert not report.integrity_valid and "file_hash_mismatch" in codes(report)


def test_claimed_stage_needs_operator_version_time_details_and_evidence(record_set):
    record_set[3][0]["stages"]["open"] = {"status": "pass_observed"}
    repin(record_set)
    report = check(record_set)
    assert not report.integrity_valid
    assert {
        "operator_required",
        "host_version_required",
        "stage_evidence_missing",
        "stage_observation_required",
    } <= codes(report)


@pytest.mark.parametrize("stage,slot", [(s, k) for s in STAGES for k in REQUIRED[s]])
def test_each_required_success_evidence_slot_is_enforced(record_set, stage, slot):
    complete_first(record_set)
    del record_set[3][0]["stages"][stage]["evidence"][slot]
    repin(record_set)
    report = check(record_set)
    assert not report.integrity_valid and "stage_evidence_missing" in codes(report)


def test_complete_claim_remains_unverified_with_other_five_pending(record_set):
    complete_first(record_set)
    report = check(record_set)
    assert report.integrity_valid
    assert report.records[0].host_status == "reported_complete"
    assert report.host_status == "incomplete" and report.stage_counts["pending_not_performed"] == 45
    assert report.host_compatibility == "unverified" and not report.execution_allowed


@pytest.mark.parametrize(
    "change,want",
    [
        ("pending_evidence", "pending_has_results"),
        ("pending_output", "pending_has_results"),
        ("missing_stage", "record_schema_invalid"),
        ("wrong_probe", "record_probe_mismatch"),
        ("duplicate_probe", "manifest_invalid"),
        ("unknown_status", "record_schema_invalid"),
        ("grant_writer", "record_schema_invalid"),
        ("blocked_no_reason", "stage_reason_required"),
        ("skipped_no_reason", "stage_reason_required"),
    ],
)
def test_contradictory_or_incomplete_records_cannot_claim_integrity(record_set, change, want):
    root, _, manifest, records = record_set
    record = records[0]
    if change == "pending_evidence":
        record["stages"]["open"]["details"] = "Claimed real observation"
    elif change == "pending_output":
        record["outputs"] = {"A": save(root / "fake-a.flp", b"claim")}
    elif change == "missing_stage":
        del record["stages"]["open"]
    elif change == "wrong_probe":
        record["probe"] = PROBES[1]
    elif change == "duplicate_probe":
        manifest["records"][0]["probe"] = PROBES[1]
    elif change == "unknown_status":
        record["stages"]["open"]["status"] = "passed"
    elif change == "grant_writer":
        record["writer_eligibility"] = "ready"
    else:
        record["stages"]["open"]["status"] = (
            "blocked" if change.startswith("blocked") else "skipped"
        )
    repin(record_set)
    report = check(record_set)
    assert not report.integrity_valid and want in codes(report)


@pytest.mark.parametrize(
    "change,want",
    [
        ("no_audio", "listening_required"),
        ("wrong_version", "host_version_required"),
        ("naive_time", "record_schema_invalid"),
        ("out_of_order", "stage_order_invalid"),
        ("output_alias", "output_overlaps_input"),
        ("missing_output", "saved_output_required"),
    ],
)
def test_claimed_complete_has_independent_prerequisites(record_set, change, want):
    complete_first(record_set)
    record = record_set[3][0]
    if change == "no_audio":
        record["listening"]["A"] = "not_listened"
    elif change == "wrong_version":
        record["actual_version"] = "26.1.8.1"
    elif change == "naive_time":
        record["stages"]["open"]["performed_at"] = "2026-10-16T04:01:00"
    elif change == "out_of_order":
        record["stages"]["reopen_a"]["performed_at"] = "2026-10-16T03:00:00-04:00"
    elif change == "output_alias":
        record["outputs"]["A"] = record_set[2]["records"][0]["candidate"]
    else:
        record["outputs"]["B"] = None
    repin(record_set)
    report = check(record_set)
    assert not report.integrity_valid and want in codes(report)


def test_missing_evidence_is_reported_even_for_failed_attempt(record_set):
    complete_first(record_set)
    record = record_set[3][0]
    record["stages"]["open"]["status"] = "fail_observed"
    evidence = record["stages"]["open"]["evidence"]["observation"]
    (record_set[0] / evidence["path"]).unlink()
    repin(record_set)
    report = check(record_set)
    assert not report.integrity_valid and "file_unavailable" in codes(report)


@pytest.mark.parametrize(
    "bad_path", ["../outside.txt", "C:/outside.txt", "dir/../x", "x:stream", "CON", "folder\\x"]
)
def test_uncontained_or_ambiguous_evidence_paths_are_rejected(record_set, bad_path):
    record_set[2]["records"][0]["form"]["path"] = bad_path
    repin(record_set)
    report = check(record_set)
    assert not report.integrity_valid and "manifest_invalid" in codes(report)


def test_size_and_mtime_are_checked_independently(record_set):
    root, _, manifest, _ = record_set
    entry = manifest["records"][0]["candidate"]
    entry["size_bytes"] += 1
    entry["mtime_ns"] = (root / entry["path"]).stat().st_mtime_ns - 1
    repin(record_set)
    report = check(record_set)
    assert {"file_size_mismatch", "file_mtime_mismatch"} <= codes(report)


def test_all_complete_claims_still_cannot_authorize_writing(record_set):
    complete_first(record_set)
    for index in range(1, 6):
        record_set[3][index] = copy.deepcopy(record_set[3][0])
        record_set[3][index]["probe"] = PROBES[index]
        for output in ("A", "B"):
            record_set[3][index]["outputs"][output] = save(
                record_set[0] / f"{index}-{output}.flp", f"authored {index} {output}".encode()
            )
    repin(record_set)
    report = check(record_set)
    assert report.integrity_valid and report.host_status == "reported_complete"
    assert report.stage_counts == {"pass_observed": 54}
    assert report.writer_eligibility == "blocked" and report.host_compatibility == "unverified"


def test_shared_host_output_across_probes_is_not_independent_evidence(record_set):
    complete_first(record_set)
    record_set[3][1] = copy.deepcopy(record_set[3][0])
    record_set[3][1]["probe"] = PROBES[1]
    repin(record_set)
    report = check(record_set)
    assert not report.integrity_valid and "output_overlaps_input" in codes(report)


def test_invalid_record_stages_are_unknown_instead_of_pending(record_set):
    root, _, manifest, _ = record_set
    (root / manifest["records"][0]["record"]["path"]).unlink()
    report = check(record_set)
    assert not report.integrity_valid
    assert report.unknown_stages == 9 and report.stage_counts["pending_not_performed"] == 45


def test_duplicate_json_keys_are_not_silently_accepted(record_set):
    root, _, manifest, _ = record_set
    raw = b'{"schema_version":1,"schema_version":1}'
    manifest["records"][0]["record"] = save(root / "default-grow.json", raw)
    record_set[1].write_text(json.dumps(manifest), encoding="utf-8")
    report = check(record_set)
    assert not report.integrity_valid and "record_schema_invalid" in codes(report)


def test_reported_success_needs_an_flp_output(record_set):
    complete_first(record_set)
    record_set[3][0]["outputs"]["A"] = save(record_set[0] / "fake.txt", b"not a host save")
    repin(record_set)
    report = check(record_set)
    assert not report.integrity_valid and "saved_output_required" in codes(report)


@pytest.mark.parametrize(
    "field,value",
    [
        ("performed_at", "2026-10-16T04:00:00-04:00"),
        ("reason", "Actually happened"),
        ("evidence", {"note": None}),
    ],
)
def test_pending_stage_cannot_hide_any_execution_fields(record_set, field, value):
    if field == "evidence":
        value = {"note": save(record_set[0] / "observed.txt", b"authored observation")}
    record_set[3][0]["stages"]["identity"][field] = value
    repin(record_set)
    report = check(record_set)
    assert not report.integrity_valid and "pending_has_results" in codes(report)


def test_a_real_failed_attempt_can_have_valid_complete_recording(record_set):
    complete_first(record_set)
    record = record_set[3][0]
    record["stages"]["open"]["status"] = "fail_observed"
    for name in STAGES[2:]:
        record["stages"][name] = {"status": "blocked", "reason": "Input could not open"}
    record["outputs"] = {}
    record["listening"] = {}
    repin(record_set)
    report = check(record_set)
    assert report.integrity_valid and report.host_status == "incomplete"
    assert report.stage_counts["fail_observed"] == 1
    assert report.stage_counts["blocked"] == 7


def test_input_change_after_first_read_invalidates_the_entire_report(record_set, monkeypatch):
    root, path, manifest, _ = record_set
    target = root / manifest["records"][0]["form"]["path"]
    original_read = Path.read_bytes
    reads = 0

    def changing_read(current):
        nonlocal reads
        raw = original_read(current)
        if current == target:
            reads += 1
            if reads == 2:
                current.write_bytes(b"changed during audit")
        return raw

    monkeypatch.setattr(Path, "read_bytes", changing_read)
    report = check(record_set)
    assert not report.integrity_valid and "input_changed_during_check" in codes(report)
    assert any(item.role.endswith("/form") and not item.valid for item in report.files)
    assert report.records[0].host_status == "incomplete"


def test_hardlinked_output_does_not_bypass_source_protection(record_set):
    complete_first(record_set)
    root, _, manifest, records = record_set
    source = root / manifest["records"][0]["candidate"]["path"]
    link = root / "alias.flp"
    try:
        link.hardlink_to(source)
    except OSError:
        pytest.skip("OS does not permit hard-link creation for this user")
    records[0]["outputs"]["A"] = {
        "path": link.name,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "size_bytes": source.stat().st_size,
    }
    repin(record_set)
    report = check(record_set)
    assert not report.integrity_valid and "output_overlaps_input" in codes(report)


def test_partial_blocked_observation_is_not_misreported_as_pending(record_set):
    root, _, _, records = record_set
    records[0].update(operator="Synthetic operator", actual_version="26.1.7.5654")
    records[0]["stages"]["identity"] = {
        "status": "blocked",
        "reason": "Could observe version but cannot confirm PPQ",
        "performed_at": "2026-10-16T04:00:00-04:00",
        "details": "Partial observation",
        "evidence": {"observation": save(root / "partial.txt", b"authored observation")},
    }
    repin(record_set)
    report = check(record_set)
    assert report.integrity_valid and report.host_status == "incomplete"
    assert (
        report.stage_counts["blocked"] == 1 and report.stage_counts["pending_not_performed"] == 53
    )


def test_final_protection_check_remains_possible_after_failed_open(record_set):
    complete_first(record_set)
    record = record_set[3][0]
    record["stages"]["open"]["status"] = "fail_observed"
    for name in STAGES[2:-1]:
        record["stages"][name] = {"status": "blocked", "reason": "Could not open input"}
    record["outputs"] = {}
    record["listening"] = {}
    repin(record_set)
    report = check(record_set)
    assert report.integrity_valid and report.host_status == "incomplete"
    assert report.stage_counts["pass_observed"] == 2


def test_linked_manifest_is_rejected_before_resolution(record_set):
    from suno2flp.validator.manual_records import check_manual_records

    root, manifest, _, _ = record_set
    link = root / "manifest-link.json"
    try:
        link.symlink_to(manifest)
    except OSError:
        pytest.skip("OS does not permit symbolic-link creation for this user")
    report = check_manual_records(link, root)
    assert not report.integrity_valid and "manifest_invalid" in codes(report)
