"""Original synthetic records; no vendor/private FLP bytes or host required."""

import json
import struct

import pytest
from typer.testing import CliRunner

from suno2flp.cli import app


def project(payload, *, version=b"26.1.7.5654\0", pattern=True, ppq=96):
    data = bytes([199, len(version)]) + version
    if pattern:
        data += bytes([65, 1, 0])
    data += bytes([223, len(payload)]) + payload
    return (
        b"FLhd" + struct.pack("<IHHH", 6, 0, 1, ppq) + b"FLdt" + struct.pack("<I", len(data)) + data
    )


def scanner():
    from suno2flp.integrations.fl26_controls import inspect_controls

    return inspect_controls


def test_integer_records_have_byte_provenance_and_keep_order():
    payload = struct.pack("<III", 96, 0x40000005, 60000) + struct.pack("<III", 0, 0, 12800)
    raw = project(payload)
    result = scanner()(raw)
    assert [r.position_raw for r in result.records] == [96, 0]
    assert [r.value_i32 for r in result.records] == [60000, 12800]
    assert [r.observation for r in result.records] == [
        "tempo_millibpm",
        "native_channel_zero_volume",
    ]
    for r in result.records:
        assert raw[r.file_offset : r.file_offset + 12].hex() == r.raw_hex
        assert r.pattern_id == 0 and r.event_index == 2
    assert result.execution_allowed is False and result.writer_eligibility == "blocked"
    assert result.timing_semantics == "unverified"


@pytest.mark.parametrize(
    "address,value", [(0x10000, 12800), (0x40000005, 0), (0x40000005, 0xFFFFFFFF), (0, 12801)]
)
def test_unobserved_addresses_or_values_not_promoted(address, value):
    result = scanner()(project(struct.pack("<III", 0, address, value)))
    assert result.records[0].observation == "unverified"
    assert result.records[0].value_u32 == value
    assert result.records[0].value_i32 == (value if value < 2**31 else value - 2**32)


def test_partial_record_retains_whole_payload_and_blocks():
    payload = struct.pack("<III", 0, 0x40000005, 120000) + b"\xff"
    result = scanner()(project(payload))
    assert result.events[0].raw_hex == payload.hex()
    assert result.events[0].tail_hex == "ff"
    assert result.records[0].observation == "unverified"
    assert "control_record_alignment" in {d.code for d in result.diagnostics}


@pytest.mark.parametrize("version", [b"25.1.2.4896\0", b"26.1.7.5654", b"26.1.8.5654\0"])
def test_exact_version_required(version):
    with pytest.raises(ValueError, match="version"):
        scanner()(project(b"", version=version))


def test_missing_pattern_and_unknown_position_are_not_interpreted():
    result = scanner()(project(struct.pack("<III", 0xFFFFFFFF, 0x40000005, 120000), pattern=False))
    assert result.records[0].position_raw == 0xFFFFFFFF
    assert result.records[0].pattern_id is None
    assert result.records[0].observation == "unverified"


def test_cli_exclusive_source_hash_and_no_write_authorization(tmp_path):
    source = tmp_path / "source.flp"
    raw = project(struct.pack("<III", 0, 0x40000005, 120000))
    source.write_bytes(raw)
    output = tmp_path / "controls.json"
    runner = CliRunner()
    result = runner.invoke(app, ["inspect-fl26-controls", str(source), "--output", str(output)])
    assert result.exit_code == 0, result.output
    saved = json.loads(output.read_text())
    assert saved["source_file"]["path"] == str(source.resolve())
    assert saved["execution_allowed"] is False
    assert "blocked" in result.output
    assert (
        runner.invoke(
            app, ["inspect-fl26-controls", str(source), "--output", str(output)]
        ).exit_code
        == 1
    )
    assert source.read_bytes() == raw


@pytest.mark.parametrize("ppq", [24, 480, 1920])
def test_unassessed_ppq_keeps_raw_fields_only(ppq):
    result = scanner()(project(struct.pack("<III", 0, 0x40000005, 120000), ppq=ppq))
    assert result.records[0].observation == "unverified"


def test_extra_chunks_and_duplicate_versions_are_rejected():
    raw = project(b"")
    with pytest.raises(ValueError, match="chunk"):
        scanner()(raw + b"JUNK\0\0\0\0")
    # Use the actual payload length, retaining a well-formed duplicate declaration.
    version = bytes([199, len(b"26.1.7.5654\0")]) + b"26.1.7.5654\0"
    changed = raw[:18] + struct.pack("<I", len(raw) - 22 + len(version)) + raw[22:] + version
    with pytest.raises(ValueError, match="version"):
        scanner()(changed)


def test_controls_before_version_fail_instead_of_retroactive_interpretation():
    raw = project(b"")
    data = bytes([223, 0]) + raw[22:]
    with pytest.raises(ValueError, match="Version"):
        scanner()(raw[:18] + struct.pack("<I", len(data)) + data)


def test_empty_payload_has_no_invented_records():
    result = scanner()(project(b""))
    assert result.records == [] and result.events[0].raw_hex == ""
    assert result.writer_eligibility == "blocked"


def test_observation_does_not_cross_product_unperformed_value_ppq_pair():
    result = scanner()(project(struct.pack("<III", 0, 0x40000005, 120001), ppq=960))
    assert result.records[0].observation == "unverified"


def test_source_change_during_publication_fails(tmp_path, monkeypatch):
    import suno2flp.cli as cli

    source = tmp_path / "source.flp"
    source.write_bytes(project(struct.pack("<III", 0, 0x40000005, 120000)))
    original = cli.new_report

    def change_after(path, content, protected):
        original(path, content, protected)
        source.write_bytes(source.read_bytes() + b"changed")

    monkeypatch.setattr(cli, "new_report", change_after)
    result = CliRunner().invoke(
        app, ["inspect-fl26-controls", str(source), "--output", str(tmp_path / "report.json")]
    )
    assert result.exit_code == 1 and "Input changed" in result.output
