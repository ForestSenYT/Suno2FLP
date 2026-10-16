"""Opt-in real fixed native codecs; no DAW, network or source media in ordinary tests."""

import json
import os
import shutil
import struct
import sys
from pathlib import Path

import pytest

from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input

pytestmark = pytest.mark.external


@pytest.fixture(scope="module")
def backend(tmp_path_factory):
    value = os.environ.get("SUNO2FLP_CODEC_WHEELHOUSE")
    if not value:
        pytest.skip("Set SUNO2FLP_CODEC_WHEELHOUSE for the explicitly prepared fixed native wheels")
    from suno2flp.integrations.codec_backend import provision_codec_backend

    return provision_codec_backend(
        tmp_path_factory.mktemp("codec-runtime") / "backend",
        Path(sys.executable),
        wheelhouse=Path(value),
    )


@pytest.fixture(scope="module")
def source_files(backend, tmp_path_factory):
    from suno2flp.integrations.codec_process import run_bounded_process

    root = tmp_path_factory.mktemp("codec-audio")
    worker = next(x.path for x in backend.adapter_files if x.path.name == "codec_worker.py")
    code = (
        "import sys,runpy,json; from pathlib import Path; "
        "m=runpy.run_path(sys.argv[1]); sf,np,_=m['_native'](Path(sys.argv[2])); "
        "p=Path(sys.argv[3]); a=np.random.default_rng(42).uniform(-.25,.25,(8192,2)); "
        "a[1000]=[.8,-.8]; a[-200]=[-.8,.8]; "
        "sf.write(p/'source.wav',a,44100,subtype='PCM_24'); "
        "a,r=sf.read(p/'source.wav',dtype='float64',always_2d=True); "
        "sf.write(p/'source.flac',a,r,subtype='PCM_24'); sf.write(p/'source.mp3',a,r); "
        "print(json.dumps({'frames':len(a),'rate':r}))"
    )
    out, err = run_bounded_process(
        [
            str(backend.python.path),
            "-I",
            "-S",
            "-B",
            "-c",
            code,
            str(worker),
            str(backend.root / "packages"),
            str(root),
        ]
    )
    assert not err and json.loads(out) == {"frames": 8192, "rate": 44100}
    return root


def worker_args(source, pcm):
    from suno2flp.importer.encoded_audio import inspect_encoded_audio

    inventory = inspect_encoded_audio(source)
    return [
        str(source),
        str(pcm),
        inventory.codec,
        str(inventory.frames),
        str(inventory.sample_rate),
        str(inventory.channels),
        str(inventory.flac.bits_per_sample if inventory.flac else 0),
        inventory.flac.pcm_md5 if inventory.flac else "-",
    ], inventory


def test_actual_handshake_and_read_only_integrity_replay(backend):
    from suno2flp.integrations.codec_backend import verify_codec_backend

    manifest = capture_stream_input(backend.root / "backend.json")
    assert verify_codec_backend(backend.root) == backend
    assert backend.probe.libsndfile_version == "1.2.2"
    assert backend.probe.versions["soundfile"] == "0.14.0"
    assert backend.probe.python_abi in ("cp311", "cp314")
    assert backend.probe.system_fallback == "forbidden" and backend.probe.no_site
    assert len(backend.payload) > 100 and backend.writer_eligibility == "blocked"
    assert capture_stream_input(manifest.path) == manifest


@pytest.mark.parametrize("codec", ["flac", "mp3"])
def test_actual_decode_and_full_current_source_replay(backend, source_files, tmp_path, codec):
    from suno2flp.importer.pcm_decode import decode_pcm_wave
    from suno2flp.integrations.codec_backend import run_codec_worker

    source = source_files / f"source.{codec}"
    before = capture_stream_input(source)
    pcm = tmp_path / "new.wav"
    args, inventory = worker_args(source, pcm)
    decoded = run_codec_worker(backend.root, "decode", args)
    checked = run_codec_worker(backend.root, "verify", args)
    assert decoded.model_dump(exclude={"mode"}) == checked.model_dump(exclude={"mode"})
    assert (decoded.frames, decoded.sample_rate, decoded.channels) == (8192, 44100, 2)
    assert decoded.source_sha256 == before.sha256 and decoded.codec == inventory.codec
    assert capture_stream_input(pcm).sha256 == decoded.pcm_sha256
    assert pcm.stat().st_size == 58 + 8192 * 2 * 8
    if codec == "flac":
        reference = decode_pcm_wave(source_files / "source.wav", tmp_path / "reference")
        assert reference.samples_sha256 == decoded.samples_sha256
        assert decoded.flac_pcm_md5 == inventory.flac.pcm_md5
    else:
        assert decoded.flac_pcm_md5 is None
    with pytest.raises((OfflineError, ValueError)):
        run_codec_worker(backend.root, "decode", args)
    assert capture_stream_input(source) == before
    # Only this newly generated candidate is changed; source/runtime remain intact.
    with pcm.open("r+b") as stream:
        stream.seek(58)
        stream.write(struct.pack("<d", 0.123456789))
    with pytest.raises(OfflineError):
        run_codec_worker(backend.root, "verify", args)


@pytest.mark.parametrize("damage", ["extra-module", "native-library", "manifest-python"])
def test_current_payload_or_executable_changes_fail_before_native_execution(
    backend, tmp_path, damage
):
    from suno2flp.integrations.codec_backend import verify_codec_backend

    clone = tmp_path / "new-copy"
    shutil.copytree(backend.root, clone)
    data = backend.model_dump(mode="json")
    data["root"] = str(clone)
    data["wheels"] = [
        capture_stream_input(clone / "wheels" / x.path.name).model_dump(mode="json")
        for x in backend.wheels
    ]
    data["probe"]["native_path"] = str(
        clone / "packages/_soundfile_data" / backend.probe.native_path.name
    )
    if damage == "extra-module":
        (clone / "packages/injected.pth").write_text("raise RuntimeError('must never execute')")
    elif damage == "native-library":
        native = Path(data["probe"]["native_path"])
        native.write_bytes(b"invalid native copy")
    else:
        fake = clone / "python.exe"
        fake.write_bytes(b"must never execute")
        data["python"] = capture_stream_input(fake).model_dump(mode="json")
    (clone / "backend.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(OfflineError) as error:
        verify_codec_backend(clone)
    assert error.value.code == (
        "audio_python_unavailable"
        if damage == "manifest-python"
        else "audio_backend_integrity_failed"
    )
    assert verify_codec_backend(backend.root) == backend


@pytest.mark.parametrize("codec", ["flac", "mp3"])
def test_shared_job_and_independent_candidate_verifier(backend, source_files, tmp_path, codec):
    from suno2flp.pipeline.audio_jobs import create_audio_job, run_audio_job, verify_audio_job
    from suno2flp.validator.encoded_decode import verify_encoded_decode

    first = create_audio_job(source_files / f"source.{codec}", tmp_path / "job", "encoded-v1")
    result = run_audio_job(first.record.path, decoder_directory=backend.root)
    assert result.job.status == "blocked" and result.job.history[-1].code == "worker_unavailable"
    assert [s.status for s in result.job.stages[:3]] == ["succeeded", "succeeded", "queued"]
    pcm, report, request = result.job.stages[1].outputs
    assert verify_encoded_decode(report.path).request == request
    assert verify_audio_job(result.record.path) == result
    preserved = [capture_stream_input(p) for p in result.job.output_directory.rglob("*.json")]
    repeated = run_audio_job(result.record.path)  # No configuration silently replaces the recipe.
    assert all(capture_stream_input(p.path) == p for p in preserved)
    assert repeated.job.stages[1].outputs == result.job.stages[1].outputs
    with pytest.raises(OfflineError, match="another runtime"):
        run_audio_job(repeated.record.path, decoder_directory=tmp_path / "different")
    # Forge all directly corresponding candidate hashes. Native source replay still refuses.
    with pcm.path.open("r+b") as stream:
        stream.seek(58)
        stream.write(struct.pack("<d", 0.123456789))
    data = json.loads(report.path.read_bytes())
    import hashlib

    changed = capture_stream_input(pcm.path)
    data["pcm"] = changed.model_dump(mode="json")
    data["native"]["pcm_sha256"] = changed.sha256
    data["native"]["samples_sha256"] = hashlib.sha256(pcm.path.read_bytes()[58:]).hexdigest()
    report.path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(OfflineError):
        verify_encoded_decode(report.path)


def test_actual_gapless_origin_every_supported_mpeg_rate_and_channel_layout(backend, tmp_path):
    from suno2flp.importer.encoded_audio import inspect_encoded_audio
    from suno2flp.integrations.codec_process import run_bounded_process

    worker = next(x.path for x in backend.adapter_files if x.path.name == "codec_worker.py")
    code = """
import sys,runpy,json
from pathlib import Path
m=runpy.run_path(sys.argv[1]); sf,np,probe=m['_native'](Path(sys.argv[2])); root=Path(sys.argv[3])
results=[]
for rate in (8000,11025,12000,16000,22050,24000,32000,44100,48000):
 for ch in (1,2):
  frames=rate//4+37
  a=np.random.default_rng(rate+ch).uniform(-.2,.2,(frames,ch))
  a[101]=.8; a[-101]=-.8
  path=root/f'{rate}-{ch}.mp3'; sf.write(path,a,rate)
  b,r=sf.read(path,dtype='float64',always_2d=True)
  assert (len(b),r,b.shape[1])==(frames,rate,ch)
  reference=a[:,0]; signal=b[:,0]
  lags=range(-1024,1025)
  scores=[float(np.dot(reference[max(0,-k):min(frames,frames-k)],
            signal[max(0,k):min(frames,frames+k)])) for k in lags]
  lag=list(lags)[int(np.argmax(scores))]
  assert lag==0,(rate,ch,lag)
  results.append({'name':path.name,'frames':frames,'rate':rate,'channels':ch,'best_lag':lag})
for depth,subtype in ((8,'PCM_S8'),(16,'PCM_16'),(24,'PCM_24')):
 a=np.random.default_rng(depth).integers(-(1<<(depth-1)),1<<(depth-1),(8193,2)).astype('float64')/(1<<(depth-1))
 path=root/f'depth-{depth}.flac'; sf.write(path,a,44100,subtype=subtype)
 b,r=sf.read(path,dtype='float64',always_2d=True)
 assert np.array_equal(a,b)
 results.append({'name':path.name,'frames':len(a),'rate':r,'channels':2,'depth':depth})
print(json.dumps(results))
"""
    out, err = run_bounded_process(
        [
            str(backend.python.path),
            "-I",
            "-S",
            "-B",
            "-c",
            code,
            str(worker),
            str(backend.root / "packages"),
            str(tmp_path),
        ]
    )
    assert not err
    results = json.loads(out)
    assert len(results) == 21
    for item in results:
        inventory = inspect_encoded_audio(tmp_path / item["name"])
        assert (inventory.frames, inventory.sample_rate, inventory.channels) == (
            item["frames"],
            item["rate"],
            item["channels"],
        )
        if inventory.flac:
            assert inventory.flac.bits_per_sample == item["depth"]
    (tmp_path / "qualification.json").write_text(json.dumps(results), encoding="utf-8")


def test_gui_model_uses_same_compressed_service_and_preserves_runtime_on_workspace_change(
    backend, source_files, tmp_path
):
    from threading import Event

    from suno2flp.gui.model import JobActions, present_job

    actions = JobActions(tmp_path / "jobs", backend.root)
    created = actions.create(source_files / "source.flac")
    result = actions.run(created.record.path, Event())
    assert present_job(result).completed == 2
    assert "没有生成 FLP" in present_job(result).explanation
    assert actions.verify(result.record.path) == result


def test_invalid_reservoir_with_valid_complete_crcs_fails_before_native(
    backend, source_files, tmp_path
):
    from suno2flp.importer.encoded_audio import inspect_encoded_audio
    from suno2flp.importer.encoded_checksums import lame_crc16
    from suno2flp.pipeline.audio_jobs import create_audio_job, run_audio_job

    source = source_files / "source.mp3"
    before = capture_stream_input(source)
    inventory = inspect_encoded_audio(source)
    data = bytearray(source.read_bytes())
    metadata = next(x for x in inventory.metadata if x.kind == "xing-lame-frame")
    audio = inventory.data_offset + metadata.size_bytes
    crc_bytes = 0 if data[audio + 1] & 1 else 2
    data[audio + 4 + crc_bytes] = 255
    data[audio + 5 + crc_bytes] |= 128
    if crc_bytes:
        from suno2flp.importer.encoded_checksums import mpeg_crc16

        data[audio + 4 : audio + 6] = mpeg_crc16(
            data[audio + 2 : audio + 4] + data[audio + 6 : audio + 38]
        ).to_bytes(2, "big")
    lame = inventory.mp3.tag_offset + len(bytes.fromhex(inventory.mp3.raw_tag_hex)) - 36
    data[lame + 32 : lame + 34] = lame_crc16(data[audio : inventory.data_end]).to_bytes(2, "big")
    data[lame + 34 : lame + 36] = lame_crc16(data[inventory.data_offset : lame + 34]).to_bytes(
        2, "big"
    )
    path = tmp_path / "invalid-reservoir.mp3"
    path.write_bytes(data)
    with pytest.raises(OfflineError, match="reservoir"):
        inspect_encoded_audio(path)
    created = create_audio_job(path, tmp_path / "job", "invalid-reservoir-v1")
    rejected = run_audio_job(created.record.path, decoder_directory=backend.root)
    assert rejected.job.status == "failed" and rejected.job.history[-1].code == "audio_invalid"
    assert rejected.job.stages[1].status == "queued" and not list(
        rejected.job.output_directory.glob("decode-*")
    )
    assert capture_stream_input(source) == before
