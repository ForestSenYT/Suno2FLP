"""Opt-in real adapted runtime; private FLP is read only, fixtures are authored here."""

import hashlib
import os
import struct
from pathlib import Path

import pytest

from suno2flp.integrations.music2daw import Music2DawInspector
from suno2flp.integrations.music2daw_provision import verify_backend

pytestmark = pytest.mark.external


def adapted_directory():
    value = os.environ.get("SUNO2FLP_FL26_ADAPTED_BACKEND")
    if not value:
        pytest.skip("Set SUNO2FLP_FL26_ADAPTED_BACKEND for the separately adapted runtime")
    return Path(value)


def test_real_fl26_adapter_reads_selected_facts_without_changing_source():
    directory = adapted_directory()
    value = os.environ.get("SUNO2FLP_FL26_TEMPLATE")
    if not value:
        pytest.skip("Set SUNO2FLP_FL26_TEMPLATE for private read-only adapter verification")
    path = Path(value)
    before, info = path.read_bytes(), path.stat()
    record, manifest = verify_backend(directory)
    report = Music2DawInspector(directory).inspect(path)
    assert report.backend_summary_status == "consistent", report.backend_summary_mismatches
    assert report.project.tempo * 1000 == report.local_summary.tempo_millibpm
    assert sum(p["noteCount"] for p in report.project.patterns) == len(report.inventory.notes)
    assert report.project.playlist_item_count == len(report.inventory.clips) > 0
    assert report.backend.adaptation.profile == "fl26-26.1.7.5654-inspect-v1"
    assert report.compatibility == "unverified"
    assert path.read_bytes() == before and path.stat().st_mtime_ns == info.st_mtime_ns
    assert hashlib.sha256(before).hexdigest() == report.template_sha256_after
    assert verify_backend(directory) == (record, manifest)


@pytest.mark.parametrize("count", [1, 4, 10, 15])
def test_adapted_runtime_does_not_fallback_to_old_playlist_strides(tmp_path, count):
    directory = adapted_directory()

    def event(kind, payload):
        if kind < 192:
            return bytes([kind]) + payload
        size, prefix = len(payload), bytearray()
        while size >= 128:
            prefix.append((size & 127) | 128)
            size >>= 7
        return bytes([kind]) + prefix + bytes([size]) + payload

    payload = event(199, b"26.1.7.5654\0") + event(172, b"\x01\x01\0")
    payload += event(156, struct.pack("<I", 123000))
    payload += event(64, b"\0\0") + event(65, b"\x01\0")
    note = bytearray(24)
    struct.pack_into("<i", note, 8, 96)
    note[12], note[21] = 60, 80
    payload += event(224, note)
    clips = []
    for index in range(count):
        clip = bytearray(88)
        struct.pack_into("<iHHiHH", clip, 0, index * 96, 2, 3, 96, 499, 0)
        clip[80:] = bytes(range(1, 9))
        clips.append(clip)
    payload += event(233, b"".join(clips))
    raw = (
        b"FLhd"
        + struct.pack("<IHHH", 6, 0, 1, 96)
        + b"FLdt"
        + struct.pack("<I", len(payload))
        + payload
    )
    path = tmp_path / "original-synthetic.flp"
    path.write_bytes(raw)
    report = Music2DawInspector(directory).inspect(path)
    assert report.backend_summary_status == "consistent"
    assert report.project.tempo == 123 and report.project.playlist_item_count == count
    assert report.project.patterns[0]["noteCount"] == 1
    assert path.read_bytes() == raw
