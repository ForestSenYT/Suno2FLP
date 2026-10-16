"""Saved-bundle checks use original synthetic bytes, never private projects."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from test_build_planning import planning_case as planning_case
from test_fl26_writer import save_case
from test_fl26_writer import writer_case as writer_case
from typer.testing import CliRunner

from suno2flp.cli import app
from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.writer_models import WriterBundleProvenance
from suno2flp.flp_builder.fl26_codec import encode_fl26
from suno2flp.flp_builder.fl26_verify import verify_fl26_output
from suno2flp.flp_builder.writer_files import plan_fl26_files


@pytest.fixture
def saved_bundle(tmp_path, writer_case):
    case = writer_case()
    inputs = save_case(tmp_path, case)
    preparation = plan_fl26_files(*inputs)
    original = case[1].template_path.read_bytes()
    output = encode_fl26(original, preparation.intent)
    proof = verify_fl26_output(original, output, preparation.intent)
    provenance = WriterBundleProvenance(
        intent=preparation.intent, input_files=preparation.input_files, verification=proof
    )
    bundle = tmp_path / "authored-synthetic-bundle"
    bundle.mkdir()
    (bundle / "project.flp").write_bytes(output)
    (bundle / "provenance.json").write_bytes(provenance.model_dump_json(indent=2).encode() + b"\n")
    (bundle / "verification.json").write_bytes(proof.model_dump_json(indent=2).encode() + b"\n")
    return bundle, inputs, provenance


def fingerprint(paths):
    return {
        path: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in paths
    }


def test_saved_bundle_revalidated_without_writes_processes_or_encoding(saved_bundle, monkeypatch):
    from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files

    bundle, inputs, provenance = saved_bundle
    paths = [*bundle.iterdir(), *[f.path for f in provenance.input_files]]
    before = fingerprint(paths)
    original_open = Path.open

    def read_only_open(path, mode="r", *args, **kwargs):
        assert not set(mode) & set("wax+"), f"Attempted write: {path}"
        return original_open(path, mode, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only verification encoded output or launched a process")

    monkeypatch.setattr(Path, "open", read_only_open)
    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr("suno2flp.flp_builder.writer_files.encode_fl26", forbidden)
    monkeypatch.setattr("suno2flp.flp_builder.fl26_codec.encode_fl26", forbidden)
    proof = verify_fl26_bundle_files(bundle, inputs[-1])
    assert proof == provenance.verification
    assert proof.note_count == 2 and proof.clip_count == 2
    assert proof.compatibility == "unverified" and proof.level == "structural_round_trip_only"
    assert fingerprint(paths) == before


@pytest.mark.parametrize("name", ["project.flp", "provenance.json", "verification.json"])
def test_missing_bundle_member_is_rejected(saved_bundle, name):
    from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files

    bundle, inputs, _ = saved_bundle
    (bundle / name).unlink()
    with pytest.raises(Suno2FLPError, match="bundle"):
        verify_fl26_bundle_files(bundle, inputs[-1])


def test_extra_bundle_member_is_rejected(saved_bundle):
    from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files

    bundle, inputs, _ = saved_bundle
    (bundle / "unreviewed.txt").write_text("extra")
    with pytest.raises(Suno2FLPError, match="bundle"):
        verify_fl26_bundle_files(bundle, inputs[-1])


@pytest.mark.parametrize("name", ["provenance.json", "verification.json"])
def test_reformatted_or_duplicate_json_sidecars_are_rejected(saved_bundle, name):
    from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files

    bundle, inputs, _ = saved_bundle
    path = bundle / name
    path.write_bytes(b'{"schema_version": 999,' + path.read_bytes()[1:])
    with pytest.raises((Suno2FLPError, ValueError)):
        verify_fl26_bundle_files(bundle, inputs[-1])


@pytest.mark.parametrize(
    "kind", ["arrangement", "inspection", "bindings", "policy", "source_midi", "template"]
)
def test_changed_original_input_is_rejected(saved_bundle, kind):
    from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files

    bundle, inputs, provenance = saved_bundle
    source = next(f.path for f in provenance.input_files if f.kind == kind)
    source.write_bytes(source.read_bytes() + b"x")
    with pytest.raises(Suno2FLPError):
        verify_fl26_bundle_files(bundle, inputs[-1])


def test_changed_backend_is_rejected(saved_bundle):
    from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files

    bundle, inputs, _ = saved_bundle
    (inputs[-1] / "publish/music2daw.dll").write_bytes(b"changed synthetic backend")
    with pytest.raises(Suno2FLPError):
        verify_fl26_bundle_files(bundle, inputs[-1])


def test_original_timestamp_only_change_is_rejected(saved_bundle):
    from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files

    bundle, inputs, provenance = saved_bundle
    source = provenance.input_files[0].path
    old = source.stat()
    os.utime(source, ns=(old.st_atime_ns, old.st_mtime_ns + 1_000_000_000))
    with pytest.raises(Suno2FLPError, match="changed"):
        verify_fl26_bundle_files(bundle, inputs[-1])


@pytest.mark.parametrize("fault", ["missing", "duplicate", "reordered", "intent"])
def test_forged_provenance_cannot_bypass_current_input_reconstruction(saved_bundle, fault):
    from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files

    bundle, inputs, provenance = saved_bundle
    if fault == "missing":
        provenance.input_files.pop(0)
    elif fault == "duplicate":
        provenance.input_files.append(provenance.input_files[0].model_copy(deep=True))
    elif fault == "reordered":
        provenance.input_files.reverse()
    else:
        provenance.intent.binding_check.parts[0].notes[0].start_tick += 1
    (bundle / "provenance.json").write_bytes(provenance.model_dump_json(indent=2).encode() + b"\n")
    with pytest.raises(Suno2FLPError, match="bundle"):
        verify_fl26_bundle_files(bundle, inputs[-1])


def test_matching_forged_output_hashes_do_not_replace_independent_reparse(saved_bundle):
    from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files
    from suno2flp.integrations.template_inventory import scan_template_inventory

    bundle, inputs, provenance = saved_bundle
    raw = bytearray((bundle / "project.flp").read_bytes())
    note = scan_template_inventory(bytes(raw)).notes[0]
    raw[note.file_offset + 12] ^= 1
    (bundle / "project.flp").write_bytes(raw)
    proof = provenance.verification
    proof.output_sha256 = hashlib.sha256(raw).hexdigest()
    (bundle / "provenance.json").write_bytes(provenance.model_dump_json(indent=2).encode() + b"\n")
    (bundle / "verification.json").write_bytes(proof.model_dump_json(indent=2).encode() + b"\n")
    with pytest.raises(Suno2FLPError):
        verify_fl26_bundle_files(bundle, inputs[-1])


def test_bundle_change_during_verification_is_rejected(saved_bundle, monkeypatch):
    from suno2flp.flp_builder import bundle_verification

    bundle, inputs, _ = saved_bundle
    original_verify = bundle_verification.verify_fl26_output

    def mutate_after_read(*args, **kwargs):
        result = original_verify(*args, **kwargs)
        (bundle / "project.flp").write_bytes(b"changed after snapshot")
        return result

    monkeypatch.setattr(bundle_verification, "verify_fl26_output", mutate_after_read)
    with pytest.raises(Suno2FLPError, match="bundle"):
        bundle_verification.verify_fl26_bundle_files(bundle, inputs[-1])


def test_bundle_can_move_while_its_original_inputs_remain_at_recorded_paths(saved_bundle):
    from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files

    bundle, inputs, provenance = saved_bundle
    moved = bundle.parent / "moved-bundle"
    bundle.rename(moved)
    assert verify_fl26_bundle_files(moved, inputs[-1]) == provenance.verification


@pytest.mark.parametrize("fault", ["verification", "missing_source", "directory_member"])
def test_inconsistent_or_incomplete_bundle_cannot_report_success(saved_bundle, fault):
    from suno2flp.flp_builder.bundle_verification import verify_fl26_bundle_files

    bundle, inputs, provenance = saved_bundle
    if fault == "verification":
        proof = provenance.verification.model_copy(deep=True)
        proof.output_sha256 = "0" * 64
        (bundle / "verification.json").write_bytes(proof.model_dump_json(indent=2).encode() + b"\n")
    elif fault == "missing_source":
        next(f.path for f in provenance.input_files if f.kind == "source_midi").unlink()
    else:
        (bundle / "project.flp").unlink()
        (bundle / "project.flp").mkdir()
    with pytest.raises((Suno2FLPError, OSError)):
        verify_fl26_bundle_files(bundle, inputs[-1])


@pytest.mark.parametrize("kind", ["policy", "source_midi", "template"])
def test_original_changed_after_output_reparse_is_rejected(saved_bundle, monkeypatch, kind):
    from suno2flp.flp_builder import bundle_verification

    bundle, inputs, provenance = saved_bundle
    original_verify = bundle_verification.verify_fl26_output
    source = next(f.path for f in provenance.input_files if f.kind == kind)

    def mutate_after_read(*args, **kwargs):
        result = original_verify(*args, **kwargs)
        source.write_bytes(source.read_bytes() + b"changed during verification")
        return result

    monkeypatch.setattr(bundle_verification, "verify_fl26_output", mutate_after_read)
    with pytest.raises(Suno2FLPError, match="changed"):
        bundle_verification.verify_fl26_bundle_files(bundle, inputs[-1])


def test_cli_reports_structural_only_and_fails_for_changed_output(saved_bundle):
    bundle, inputs, _ = saved_bundle
    runner = CliRunner()
    command = ["verify-flp-bundle", str(bundle), "--backend-dir", str(inputs[-1])]
    result = runner.invoke(app, command)
    assert result.exit_code == 0, result.output
    proof = json.loads(result.output)
    assert proof["level"] == "structural_round_trip_only"
    assert proof["compatibility"] == "unverified"
    (bundle / "project.flp").write_bytes(b"damaged synthetic FLP")
    result = runner.invoke(app, command)
    assert result.exit_code == 1 and "Error:" in result.output
