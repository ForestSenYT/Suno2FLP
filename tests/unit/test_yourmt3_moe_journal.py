"""Retain every returned generation even when the retry or validation fails."""

import json
from copy import deepcopy

import pytest

from suno2flp.integrations import yourmt3_moe_worker as worker


def initial():
    return [[[0] * 256 for _ in range(13)]]


def run_window(tmp_path, generate):
    return worker.infer_window(generate, tmp_path, index=2, start=65534, valid=32767)


def read(tmp_path, phase):
    return json.loads((tmp_path / f"generation-002-{phase}.json").read_bytes())


def test_retry_failure_keeps_complete_initial_return(tmp_path):
    raw = initial()

    def generate(limit):
        if limit == 1024:
            raise RuntimeError("native retry failed")
        return deepcopy(raw)

    with pytest.raises(RuntimeError, match="native retry failed"):
        run_window(tmp_path, generate)
    assert read(tmp_path, "initial") == {
        "index": 2,
        "start_frame": 65534,
        "valid_frames": 32767,
        "max_token_length": 256,
        "tokens": raw,
    }
    assert not (tmp_path / "generation-002-retry.json").exists()
    assert not (tmp_path / "window-002.json").exists()


def test_changed_prefix_keeps_both_unmodified_returns(tmp_path):
    first = initial()
    retry = [[stream + [1] for stream in first[0]]]
    retry[0][4][0] = 2
    with pytest.raises(ValueError, match="changed initial"):
        run_window(tmp_path, lambda limit: deepcopy(first if limit == 256 else retry))
    assert read(tmp_path, "initial")["tokens"] == first
    assert read(tmp_path, "retry")["tokens"] == retry
    assert not (tmp_path / "window-002.json").exists()


def test_wrong_dimensions_retains_return_before_geometry_checks(tmp_path):
    raw = [[[0, 1]]]
    with pytest.raises(ValueError, match="dimensions"):
        run_window(tmp_path, lambda limit: deepcopy(raw))
    assert read(tmp_path, "initial")["tokens"] == raw
    assert not (tmp_path / "window-002.json").exists()


def test_wrong_retry_dimensions_preserves_both_returns(tmp_path):
    first, retry = initial(), [[[0, 1]]]
    with pytest.raises(ValueError, match="dimensions"):
        run_window(tmp_path, lambda limit: deepcopy(first if limit == 256 else retry))
    assert read(tmp_path, "initial")["tokens"] == first
    assert read(tmp_path, "retry")["tokens"] == retry
    assert not (tmp_path / "window-002.json").exists()


def test_complete_window_retains_both_returns_and_final_trace(tmp_path):
    first = initial()
    retry = [[stream + [1] for stream in first[0]]]
    result = run_window(tmp_path, lambda limit: deepcopy(first if limit == 256 else retry))
    assert read(tmp_path, "initial")["tokens"] == first
    assert read(tmp_path, "retry")["tokens"] == retry
    assert json.loads((tmp_path / "window-002.json").read_bytes()) == result
    assert [stream["tokens"] for stream in result["initial"]] == first[0]
    assert [stream["tokens"] for stream in result["retry"]] == retry[0]
    with pytest.raises(FileExistsError):
        run_window(tmp_path, lambda limit: deepcopy(first))
    assert read(tmp_path, "initial")["tokens"] == first
