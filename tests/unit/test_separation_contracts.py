"""Logical evidence geometry only; these fixtures do not claim a real model run."""

import importlib
from pathlib import Path

import pytest

from suno2flp.core.offline_models import FileIdentity

STEMS = ("vocals", "drums", "bass", "other")


def contracts():
    return importlib.import_module("suno2flp.core.separation")


def identity(root: Path, name: str, size: int, digest: str = "1"):
    return FileIdentity(path=root / name, size_bytes=size, sha256=digest * 64, mtime_ns=0)


def candidate_values(root: Path):
    clock = importlib.import_module("suno2flp.core.separation_clock")
    part = clock.plan_separation_partitions(5)[0].model_dump()
    hashes = dict(zip(STEMS, [str(index) * 64 for index in range(2, 6)], strict=True))
    result = dict(
        execution=dict(
            graph_profile="spleeter4-cpu-no-remapping-v1",
            device_types=["CPU"],
            intra_op_threads=8,
            inter_op_threads=1,
            versions={},
            modules={},
            restored_variables={"authored_fixture": [1]},
            restored_values_sha256="1" * 64,
            tfio_loaded=False,
            ambient_plugins_enabled=False,
        ),
        source_frames=5,
        sample_rate=48000,
        source_channels=1,
        model_frames=5,
        returned_source_frames=6,
        model_input_sha256="1" * 64,
        partitions=[dict(partition=part, input_sha256="1" * 64, output_sha256=hashes)],
        model_output_sha256=hashes,
        source_output_sha256=hashes,
        resampling_tail_sha256=hashes,
        peak_working_set_bytes=1024**2,
        peak_commit_bytes=1024**2,
        elapsed_seconds=0.01,
    )
    one = identity(root, "dependency.bin", 1)
    return dict(
        decode_report=identity(root, "decode.json", 1),
        source_audio=one,
        pcm=identity(root, "pcm.wav", 98),
        frames=5,
        sample_rate=48000,
        channels=1,
        decode_dependencies=[one],
        decoder_payload_root=None,
        backend_record=identity(root, "backend/backend.json", 1),
        backend=dict(
            root=root / "backend",
            python=one,
            runtime=[one],
            artifacts=[],
            adapters=[one],
            payload={"one": "1" * 64},
        ),
        model_dependencies=[one],
        recipe=dict(
            python_executable=one, python_version="fixture", pydantic_version="fixture", files=[one]
        ),
        result=result,
        model_input=identity(root, "model-input.f32", 40),
        partitions=[
            dict(
                partition=part,
                input=identity(root, "part.input.f32", 65536),
                outputs=[
                    dict(stem=stem, file=identity(root, f"part.{stem}.f32", 65536, str(index)))
                    for index, stem in enumerate(STEMS, 2)
                ],
            )
        ],
        stems=[
            dict(
                stem=stem,
                model=identity(root, f"model.{stem}.f32", 40, str(index)),
                source=identity(root, f"{stem}.wav", 98, str(index)),
                tail=identity(root, f"{stem}.tail.f32", 8, str(index)),
            )
            for index, stem in enumerate(STEMS, 2)
        ],
        residual=identity(root, "unassigned.f64", 80),
        residual_peak=0.1,
        conservation_error=0.0,
        native_result=identity(root, "result.json", 1),
        native_request=identity(root, "request.json", 1),
        stdout=identity(root, "stdout.bin", 0),
        stderr=identity(root, "stderr.bin", 0),
    )


def test_candidate_retains_source_grid_and_unqualified_status(tmp_path):
    module = contracts()
    report = module.SeparationCandidate(**candidate_values(tmp_path))
    assert report.frames == 5 and report.result.returned_source_frames == 6
    assert report.output_channels == 2
    assert [stem.stem for stem in report.stems] == list(STEMS)
    assert report.origin == "inferred_candidate" and not report.execution_allowed
    assert report.model_qualification == "not_assessed" and report.writer_eligibility == "blocked"
    assert report.ground_truth_metrics == "unavailable"


@pytest.mark.parametrize("profile", [None, "spleeter4-cpu-default-v1"])
def test_execution_without_fixed_graph_policy_is_rejected(tmp_path, profile):
    from suno2flp.core.separation_runtime import SpleeterExecution

    execution = candidate_values(tmp_path)["result"]["execution"]
    execution.pop("graph_profile", None)
    if profile is not None:
        execution["graph_profile"] = profile
    with pytest.raises(ValueError, match="graph_profile"):
        SpleeterExecution.model_validate(execution)


@pytest.mark.parametrize(
    "mutation",
    [
        "clock",
        "pcm",
        "model-input",
        "source-wav",
        "tail",
        "partial",
        "residual",
        "order",
        "partial-hash",
        "qualified",
    ],
)
def test_incomplete_or_falsely_qualified_candidate_is_rejected(tmp_path, mutation):
    module = contracts()
    report = module.SeparationCandidate(**candidate_values(tmp_path))
    raw = report.model_dump()
    if mutation == "clock":
        raw["sample_rate"] = 44100
    elif mutation in ("pcm", "model-input", "residual"):
        key = {"model-input": "model_input"}.get(mutation, mutation)
        raw[key]["size_bytes"] -= 4
    elif mutation in ("source-wav", "tail"):
        key = "source" if mutation == "source-wav" else "tail"
        raw["stems"][0][key]["size_bytes"] -= 4
    elif mutation == "partial":
        raw["partitions"][0]["outputs"].pop()
    elif mutation == "order":
        raw["stems"].reverse()
    elif mutation == "partial-hash":
        raw["partitions"][0]["input"]["sha256"] = "f" * 64
    else:
        raw["model_qualification"] = "qualified"
    with pytest.raises(ValueError):
        module.SeparationCandidate.model_validate(raw)


@pytest.mark.parametrize(
    "mutation",
    ["missing-part", "duplicate-part", "geometry", "bool", "tail-count", "memory", "stem-keys"],
)
def test_native_result_cannot_hide_missing_work_or_resource_failure(tmp_path, mutation):
    module = contracts()
    raw = candidate_values(tmp_path)["result"]
    if mutation == "missing-part":
        raw["partitions"] = []
    elif mutation == "duplicate-part":
        raw["partitions"] *= 2
    elif mutation == "geometry":
        raw["model_frames"] = 4
    elif mutation == "bool":
        raw["source_channels"] = True
    elif mutation == "tail-count":
        raw["returned_source_frames"] = 5
    elif mutation == "memory":
        raw["peak_working_set_bytes"] = 16 * 1024**3 + 1
    else:
        raw["source_output_sha256"].pop("bass")
    with pytest.raises(ValueError):
        module.NativeSeparationResult(**raw)
