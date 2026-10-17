"""Synthetic complete producer boundaries; no actual models, host or user assets."""

import pytest
from test_audio_flp import fixtures
from test_percussion_arrangement_files import current_inputs as current_inputs
from test_stem_transcription import batch as batch
from test_stem_transcription import protocol as protocol
from test_stem_transcription import recipe as recipe

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.flp_builder import audio_profile
from suno2flp.pipeline.audio_flp import export_audio_flp, verify_audio_flp_export
from suno2flp.pipeline.estimated_midi import export_estimated_midi


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
def test_current_source_publication_verification_and_no_native_calls(
    current_inputs, tmp_path, monkeypatch
):
    import hashlib

    base, sample = fixtures()
    monkeypatch.setattr(audio_profile, "BASE_SHA256", hashlib.sha256(base).hexdigest())
    monkeypatch.setattr(audio_profile, "SAMPLER_SHA256", hashlib.sha256(sample).hexdigest())
    component_root = tmp_path / "components"
    component_root.mkdir()
    a = component_root / "base.flp"
    b = component_root / "sampler.flp"
    a.write_bytes(base)
    b.write_bytes(sample)
    current = current_inputs
    source = tmp_path / "midi"
    export_estimated_midi(current.batch, current.drums, source)
    protected = [capture_stream_input(p) for p in (current.source, a, b, source / "candidate.mid")]
    calls = len(current.pitch_calls), len(current.drum_calls)
    root = tmp_path / "new bundle"
    result = export_audio_flp(source / "estimated-midi.json", a, b, root)
    assert result.status == "unqualified_candidate" and result.host_compatibility == "unverified"
    assert (root / "project.flp").is_file() and len(list((root / "audio").glob("*.wav"))) == 9
    assert verify_audio_flp_export(root / "audio-flp.json") == result
    assert calls == (len(current.pitch_calls), len(current.drum_calls))
    assert protected == [capture_stream_input(i.path) for i in protected]
    with pytest.raises(ValueError):
        export_audio_flp(source / "estimated-midi.json", a, b, root)
    (root / "audio/drum-36.wav").write_bytes(b"tampered")
    with pytest.raises((ValueError, Suno2FLPError)):
        verify_audio_flp_export(root / "audio-flp.json")


def test_missing_components_and_existing_destination_fail_before_source_load(tmp_path, monkeypatch):
    import suno2flp.pipeline.audio_flp as workflow

    def forbidden(*args, **kwargs):
        raise AssertionError("Expensive load must not run")

    monkeypatch.setattr(workflow, "load_audio_midi", forbidden)
    output = tmp_path / "already"
    output.mkdir()
    with pytest.raises(ValueError):
        export_audio_flp(tmp_path / "no.json", tmp_path / "a", tmp_path / "b", output)


def test_current_recipe_includes_executed_parser_dependencies():
    from pathlib import Path

    from suno2flp.pipeline.audio_flp import audio_flp_recipe

    package = Path(audio_profile.__file__).resolve().parent.parent
    files = {i.path for i in audio_flp_recipe().files}
    for name in (
        "integrations/template_inventory.py",
        "core/template_inventory.py",
        "core/template_profiles.py",
    ):
        assert package / name in files


@pytest.mark.parametrize("alias_kind", ["traversal", "symlink"])
def test_builtin_runtime_uses_real_executable_identity(tmp_path, monkeypatch, alias_kind):
    import errno
    import sys
    from importlib.machinery import ModuleSpec
    from pathlib import Path
    from types import SimpleNamespace

    import suno2flp.pipeline.audio_flp as service

    runtime = Path(sys.executable).resolve(strict=True)
    before = capture_stream_input(runtime)
    if alias_kind == "traversal":
        alias = runtime.parent / ".." / runtime.parent.name / runtime.name
    else:
        alias = tmp_path / "runtime-alias"
        try:
            alias.symlink_to(runtime)
        except OSError as error:
            if getattr(error, "winerror", None) != 1314 and error.errno not in (
                errno.EPERM,
                errno.EACCES,
                errno.ENOSYS,
            ):
                raise
            pytest.skip(f"Synthetic runtime symlink unavailable: {error}")
    monkeypatch.setattr(
        service,
        "sys",
        SimpleNamespace(
            platform="linux",
            executable=str(alias),
            base_prefix=sys.base_prefix,
            version_info=sys.version_info,
        ),
    )
    monkeypatch.setattr(
        service,
        "math",
        SimpleNamespace(__spec__=ModuleSpec("math", loader=None, origin="built-in")),
    )
    paths = {i.path for i in service.audio_flp_recipe().files}
    assert runtime in paths and alias not in paths
    assert capture_stream_input(runtime) == before


@pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)
@pytest.mark.parametrize("mutation", ["artifact", "membership"])
@pytest.mark.parametrize("boundary", ["publication", "verification"])
def test_final_source_guard_cannot_accept_changed_outputs(
    current_inputs, tmp_path, monkeypatch, mutation, boundary
):
    import hashlib

    import suno2flp.pipeline.audio_flp as service

    base, sample = fixtures()
    monkeypatch.setattr(audio_profile, "BASE_SHA256", hashlib.sha256(base).hexdigest())
    monkeypatch.setattr(audio_profile, "SAMPLER_SHA256", hashlib.sha256(sample).hexdigest())
    component_root = tmp_path / "components"
    component_root.mkdir()
    a = component_root / "base.flp"
    b = component_root / "sampler.flp"
    a.write_bytes(base)
    b.write_bytes(sample)
    source = tmp_path / "midi"
    export_estimated_midi(current_inputs.batch, current_inputs.drums, source)
    root = tmp_path / "candidate"
    original = service.load_audio_midi
    if boundary == "verification":
        service.export_audio_flp(source / "estimated-midi.json", a, b, root)
        completion = capture_stream_input(root / "audio-flp.json")

    def load(*args, **kwargs):
        saved, identity, raw, protected, recheck = original(*args, **kwargs)

        def late():
            recheck()
            if mutation == "artifact":
                (root / "project.flp").write_bytes(b"changed during source guard")
            else:
                (root / "unlisted.txt").write_text("late extra member")

        return saved, identity, raw, protected, late

    monkeypatch.setattr(service, "load_audio_midi", load)
    with pytest.raises((ValueError, Suno2FLPError)):
        if boundary == "publication":
            service.export_audio_flp(source / "estimated-midi.json", a, b, root)
        else:
            service.verify_audio_flp_export(root / "audio-flp.json")
    if boundary == "publication":
        assert not (root / "audio-flp.json").exists()
    else:
        assert capture_stream_input(root / "audio-flp.json") == completion
