"""Real pinned-package fixture and owned-process simulation; not a native graph test."""

import json
from pathlib import Path

import pytest
from test_spleeter_backend import recipe as recipe

from suno2flp.core.errors import Suno2FLPError


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "payload",
        "request",
        "source",
        "operation",
        "cancel",
        "result-version",
        "result-count",
        "source-result",
    ],
)
def test_separation_call_binds_request_source_and_current_backend(
    recipe, tmp_path, monkeypatch, mutation
):
    backend, artifacts, pins, _, _ = recipe
    record = backend.provision_spleeter(tmp_path / "backend", artifacts)
    attempt = tmp_path / "native"
    attempt.mkdir()
    source = tmp_path / "pcm.wav"
    source.write_bytes(b"synthetic owned source identity; worker is simulated")
    request = dict(operation="separate", pcm=str(source), frames=3, sample_rate=48000, channels=1)
    if mutation == "operation":
        request["operation"] = "write-flp"

    def process(argv, **kwargs):
        assert argv[1:4] == ["-I", "-S", "-B"] and kwargs["timeout"] == 1800
        path = Path(argv[-1])
        assert json.loads(path.read_text()) == {
            **request,
            "packages": str(record.root / "packages"),
        }
        if mutation == "payload":
            (record.root / "packages/extra.py").write_bytes(b"changed")
        elif mutation == "request":
            path.write_text("{}")
        elif mutation == "source":
            source.write_bytes(b"changed source")
        elif mutation == "cancel":
            raise RuntimeError("cancelled owned process")
        proof = dict(
            device_types=["CPU"],
            intra_op_threads=8,
            inter_op_threads=1,
            versions={pin.distribution: pin.version for pin in pins.artifacts},
            modules={
                name: str(record.root / "packages" / name.replace(".", "/") / "__init__.py")
                for name in (
                    "numpy",
                    "tensorflow",
                    "keras",
                    "scipy",
                    "pandas",
                    "spleeter",
                    "spleeter.model",
                )
            },
            restored_variables={"authored_fixture": [1]},
            restored_values_sha256="1" * 64,
            tfio_loaded=False,
            ambient_plugins_enabled=False,
        )
        hashes = {stem: "1" * 64 for stem in ("vocals", "drums", "bass", "other")}
        result = dict(
            execution=proof,
            source_frames=3,
            sample_rate=48000,
            source_channels=1,
            model_frames=3,
            returned_source_frames=4,
            model_input_sha256="1" * 64,
            partitions=[
                dict(
                    partition=dict(
                        index=0,
                        stft_start=0,
                        stft_frames=5,
                        virtual_start=-4096,
                        waveform_frames=8192,
                    ),
                    input_sha256="1" * 64,
                    output_sha256=hashes,
                )
            ],
            model_output_sha256=hashes,
            source_output_sha256=hashes,
            resampling_tail_sha256=hashes,
            peak_working_set_bytes=1024**2,
            peak_commit_bytes=1024**2,
            elapsed_seconds=0.01,
        )
        if mutation == "result-version":
            proof["versions"]["numpy"] = "incorrect"
        elif mutation == "result-count":
            result["model_frames"] = 4
        elif mutation == "source-result":
            result.update(source_frames=4, model_frames=4, returned_source_frames=5)
        (attempt / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return b"simulated transport only", b"preserved diagnostics"

    monkeypatch.setattr(backend, "run_bounded_process", process)
    call = backend.call_spleeter_separation
    if mutation:
        with pytest.raises((ValueError, RuntimeError, Suno2FLPError)):
            call(record, attempt, request)
        if mutation != "operation":
            assert (attempt / "stderr.bin").exists()
        else:
            assert not (attempt / "request.json").exists()
    else:
        identity, native = call(record, attempt, request)
        assert identity.path == attempt / "result.json"
        assert native.source_frames == 3 and native.model_frames == 3
        assert (attempt / "stdout.bin").read_bytes() == b"simulated transport only"
        assert (attempt / "stderr.bin").read_bytes() == b"preserved diagnostics"
    assert not (attempt / "separation.json").exists()
