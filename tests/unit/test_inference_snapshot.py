"""Invocation-local immutable file guards, never inference or model qualification."""

import importlib
import os

import pytest

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import capture_stream_input


def snapshot_type():
    return importlib.import_module("suno2flp.core.inference_snapshot").InferenceSnapshot


@pytest.fixture
def evidence(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"original source")
    payload = tmp_path / "packages"
    payload.mkdir()
    (payload / "module.py").write_bytes(b"original module")
    return source, payload


def test_complete_current_duplicate_references_are_read_only(evidence):
    source, payload = evidence
    source_id, members = capture_stream_input(source), capture_file_tree(payload)
    guard = snapshot_type().capture(
        [source_id, source_id, *members], [(payload, members), (payload, members)]
    )
    guard.recheck()
    assert capture_stream_input(source) == source_id
    assert capture_file_tree(payload) == members


@pytest.mark.parametrize("changed", ["source", "module", "extra", "missing", "report"])
def test_every_current_input_and_complete_payload_membership_is_rechecked(
    evidence, tmp_path, changed
):
    source, payload = evidence
    report = tmp_path / "complete.json"
    report.write_bytes(b'{"status":"candidate"}')
    guard = snapshot_type().capture(
        [capture_stream_input(source), capture_stream_input(report)],
        [(payload, capture_file_tree(payload))],
    )
    directory_time = payload.stat().st_mtime_ns
    target = {
        "source": source,
        "module": payload / "module.py",
        "extra": payload / "extra.py",
        "missing": payload / "module.py",
        "report": report,
    }[changed]
    if changed == "missing":
        target.unlink()
    else:
        target.write_bytes(b"changed bytes")
    # Restoring directory time must not hide newly introduced members.
    os.utime(payload, ns=(directory_time, directory_time))
    with pytest.raises((ValueError, Suno2FLPError)):
        guard.recheck()


def test_caller_rehashing_mutable_declarations_cannot_rewrite_the_guard(evidence):
    source, payload = evidence
    identity = capture_stream_input(source)
    members = capture_file_tree(payload)
    guard = snapshot_type().capture([identity], [(payload, members)])
    source.write_bytes(b"coherently rehashed replacement")
    replacement = capture_stream_input(source)
    identity.sha256, identity.size_bytes, identity.mtime_ns = (
        replacement.sha256,
        replacement.size_bytes,
        replacement.mtime_ns,
    )
    with pytest.raises((ValueError, Suno2FLPError)):
        guard.recheck()


def test_conflicting_or_foreign_expected_declarations_cannot_be_captured(evidence):
    source, payload = evidence
    identity = capture_stream_input(source)
    conflict = identity.model_copy(update={"sha256": "0" * 64})
    with pytest.raises(ValueError):
        snapshot_type().capture([identity, conflict], [])
    with pytest.raises(ValueError):
        snapshot_type().capture([], [(payload, [identity])])


def test_stale_inputs_and_cancellation_never_establish_or_reuse_a_guard(evidence):
    source, payload = evidence
    identity, members = capture_stream_input(source), capture_file_tree(payload)
    with pytest.raises(DecodeCancelled):
        snapshot_type().capture([identity], [(payload, members)], should_cancel=lambda: True)
    guard = snapshot_type().capture([identity], [(payload, members)])
    with pytest.raises(DecodeCancelled):
        guard.recheck(should_cancel=lambda: True)
    source.write_bytes(b"changed before capture")
    with pytest.raises((ValueError, Suno2FLPError)):
        snapshot_type().capture([identity], [(payload, members)])


def test_native_output_budget_is_distinct_from_model_budget(evidence, monkeypatch):
    source, payload = evidence
    module = importlib.import_module("suno2flp.core.inference_snapshot")
    member = capture_file_tree(payload)[0]
    # The supported 360s/192kHz geometry exceeds 3GiB. Avoid allocating that data:
    # this boundary double enforces the same aggregate byte check as the real walker.
    size = 3_485_897_192
    member = member.model_copy(update={"size_bytes": size})
    observed = []

    def tree(root, *, max_bytes, **kwargs):
        observed.append(max_bytes)
        if size > max_bytes:
            raise ValueError("Payload tree exceeds budget")
        return [member]

    monkeypatch.setattr(module, "capture_file_tree", tree)
    with pytest.raises(ValueError, match="exceeds budget"):
        module.InferenceSnapshot.capture([], [(payload, [member])])
    limits = {payload: size}
    guard = module.InferenceSnapshot.capture([], [(payload, [member])], payload_byte_limits=limits)
    limits[payload] = 1  # Later caller mutation cannot change the captured budget.
    guard.recheck()
    assert observed == [3 * 1024**3, size, size]


def test_real_tree_still_enforces_explicit_native_budget(evidence):
    source, payload = evidence
    members = capture_file_tree(payload)
    size = sum(i.size_bytes for i in members)
    with pytest.raises(ValueError, match="exceeds budget"):
        snapshot_type().capture([], [(payload, members)], payload_byte_limits={payload: size - 1})
    guard = snapshot_type().capture([], [(payload, members)], payload_byte_limits={payload: size})
    (payload / "extra.bin").write_bytes(b"unlisted")
    with pytest.raises(ValueError):
        guard.recheck()


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_or_unbound_tree_budget_is_rejected(evidence, limit):
    source, payload = evidence
    members = capture_file_tree(payload)
    with pytest.raises(ValueError, match="budget"):
        snapshot_type().capture([], [(payload, members)], payload_byte_limits={payload: limit})
    with pytest.raises(ValueError, match="budget"):
        snapshot_type().capture([], [(payload, members)], payload_byte_limits={source: 10})


def test_model_file_count_budget_is_explicit_and_frozen(evidence, monkeypatch):
    _, payload = evidence
    module = importlib.import_module("suno2flp.core.inference_snapshot")
    members = capture_file_tree(payload)
    observed = []

    # The real MoE payload has22738 members, above the generic20000 default.
    # Exercise that boundary without generating tens of thousands of files.
    def tree(root, *, max_files=20000, **kwargs):
        observed.append(max_files)
        if max_files < 22738:
            raise ValueError("Payload tree exceeds budget")
        return members

    monkeypatch.setattr(module, "capture_file_tree", tree)
    with pytest.raises(ValueError, match="exceeds budget"):
        module.InferenceSnapshot.capture([], [(payload, members)])
    limits = {payload: 30000}
    guard = module.InferenceSnapshot.capture([], [(payload, members)], payload_file_limits=limits)
    limits[payload] = 1
    guard.recheck()
    assert observed == [20000, 30000, 30000]


def test_real_file_count_budget_keeps_membership_and_byte_guards(evidence):
    _, payload = evidence
    (payload / "second.bin").write_bytes(b"original second")
    members = capture_file_tree(payload)
    with pytest.raises(ValueError, match="exceeds budget"):
        snapshot_type().capture([], [(payload, members)], payload_file_limits={payload: 1})
    size = sum(i.size_bytes for i in members)
    with pytest.raises(ValueError, match="exceeds budget"):
        snapshot_type().capture(
            [],
            [(payload, members)],
            payload_file_limits={payload: 3},
            payload_byte_limits={payload: size - 1},
        )
    guard = snapshot_type().capture([], [(payload, members)], payload_file_limits={payload: 3})
    (payload / "extra.bin").write_bytes(b"unlisted")
    with pytest.raises(ValueError, match="complete inference payload"):
        guard.recheck()


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_or_foreign_file_count_budget_is_refused(evidence, limit):
    source, payload = evidence
    members = capture_file_tree(payload)
    with pytest.raises(ValueError, match="budget"):
        snapshot_type().capture([], [(payload, members)], payload_file_limits={payload: limit})
    with pytest.raises(ValueError, match="budget"):
        snapshot_type().capture([], [(payload, members)], payload_file_limits={source: 3})
