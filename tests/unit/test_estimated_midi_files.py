"""Current tiny producer boundaries, exclusive publication and no model replay."""

import pytest
from test_percussion_arrangement_files import current_inputs as current_inputs
from test_stem_transcription import batch as batch
from test_stem_transcription import protocol as protocol
from test_stem_transcription import recipe as recipe

from suno2flp.core.errors import Suno2FLPError
from suno2flp.core.offline_files import capture_stream_input
from suno2flp.pipeline.estimated_midi import export_estimated_midi, verify_estimated_midi_export
from suno2flp.validator.midi_preview import verify_estimated_midi

pytestmark = pytest.mark.parametrize("protocol", [(1025, 2)], indirect=True)


def test_complete_export_uses_current_producers_without_new_native_calls(current_inputs, tmp_path):
    source = current_inputs
    identities = [capture_stream_input(p) for p in (source.source, source.batch, source.drums)]
    calls = len(source.pitch_calls), len(source.drum_calls)
    output = tmp_path / "preview"
    record = export_estimated_midi(source.batch, source.drums, output)
    assert record.root == output
    assert record.midi.path == output / "candidate.mid"
    assert (output / "estimated-midi.json").exists()
    assert verify_estimated_midi_export(output / "estimated-midi.json") == record
    assert record.score.arrangement.inputs.drums.transcription == identities[2]
    verify_estimated_midi(record.midi.path.read_bytes(), record.score)
    assert (len(source.pitch_calls), len(source.drum_calls)) == calls == (3, 1)
    assert [capture_stream_input(i.path) for i in identities] == identities
    with pytest.raises(ValueError):
        export_estimated_midi(source.batch, source.drums, output)
    with pytest.raises(ValueError):
        export_estimated_midi(source.batch, source.drums, source.drums.parent / "nested")
    altered = record.model_dump(mode="json")
    altered["score"]["parts"][1]["notes"][0]["pitch"] += 1
    import json

    (output / "estimated-midi.json").write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_estimated_midi_export(output / "estimated-midi.json")


@pytest.mark.parametrize("change", ["midi", "native-member", "cancel"])
def test_late_changes_or_cancel_never_publish_completion(
    current_inputs, tmp_path, monkeypatch, change
):
    import suno2flp.pipeline.estimated_midi as service

    source = current_inputs
    output = tmp_path / "preview"
    publish = service.publish_verified_report
    cancelled = False

    def late(path, content, protected, verify):
        def check():
            nonlocal cancelled
            if change == "midi":
                with (output / "candidate.mid").open("ab") as stream:
                    stream.write(b"unexpected")
            elif change == "native-member":
                (source.native_roots["vocals"] / "unexpected.json").write_text("{}")
            else:
                cancelled = True
            verify()

        return publish(path, content, protected, check)

    monkeypatch.setattr(service, "publish_verified_report", late)
    with pytest.raises((Suno2FLPError, OSError, ValueError)):
        export_estimated_midi(source.batch, source.drums, output, should_cancel=lambda: cancelled)
    assert not (output / "estimated-midi.json").exists()
