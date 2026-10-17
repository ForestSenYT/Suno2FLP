"""Second consumer of fresh decoding evidence, without a native model dependency."""

import wave
from pathlib import Path

import pytest

from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input, verify_inputs
from suno2flp.importer.pcm_decode import decode_pcm_wave
from suno2flp.validator.transcription import transcription_recipe
from suno2flp.validator.transcription_source import verified_transcription_source


def test_pcm_clock_and_all_source_witnesses_are_retained(tmp_path: Path) -> None:
    source = tmp_path / "original.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0\0" * 2000)
    output = tmp_path / "decoded"
    report = decode_pcm_wave(source, output)
    result = verified_transcription_source(output / "decode.json")
    assert (result.frames, result.sample_rate, result.channels) == (2000, 8000, 1)
    assert result.pcm == report.pcm
    assert source.resolve() in {w.path for w in result.dependencies}
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(Exception, match="changed|mismatch|size"):
        verified_transcription_source(output / "decode.json")


@pytest.mark.parametrize("alias_kind", ["parent", "symlink"])
def test_recipe_binds_resolved_running_python_without_relaxing_input_paths(
    tmp_path, monkeypatch, alias_kind
):
    runtime = tmp_path / "runtime.bin"
    runtime.write_bytes(b"already running application runtime fixture")
    if alias_kind == "parent":
        (tmp_path / "alias").mkdir()
        alias = tmp_path / "alias" / ".." / runtime.name
    else:
        alias = tmp_path / "python-link"
        try:
            alias.symlink_to(runtime)
        except OSError:
            pytest.skip("This environment cannot create file symlinks")
    monkeypatch.setattr("suno2flp.validator.transcription.sys.executable", str(alias))
    recipe = transcription_recipe()
    assert recipe.python_executable.path == runtime
    assert recipe.python_executable.size_bytes == 43
    with pytest.raises(OfflineError):
        capture_stream_input(alias)
    runtime.write_bytes(b"changed runtime")
    with pytest.raises(OfflineError):
        verify_inputs([recipe.python_executable])
