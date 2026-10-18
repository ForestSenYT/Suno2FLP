"""Original inert archives; no downloads, Torch import or real checkpoint."""

import hashlib
import importlib
import zipfile

import pytest

from suno2flp.core.errors import OfflineError
from suno2flp.core.offline_files import capture_stream_input


def api():
    assert importlib.util.find_spec("suno2flp.integrations.yourmt3_source"), "Missing inert recipe"
    return importlib.import_module("suno2flp.integrations.yourmt3_source")


def test_fixed_recipe_has_explicit_complete_state_and_license_lineage():
    pins = api().load_yourmt3_pins()
    assert len(pins.wheels) == 59
    assert len(pins.state) == 386
    assert sum(t.dtype == "torch.int64" for t in pins.state.values()) == 6
    assert all(p.notices and p.url.startswith("https://") for p in pins.wheels)
    checkpoint = next(p for p in pins.files if p.target == "models/model.ckpt")
    assert checkpoint.size_bytes == 361050039
    assert checkpoint.sha256 == "507ff129bf68f65b3b3439368706fc413523fc729d994e4da2c3f50860b05dde"
    assert checkpoint.license == "Apache-2.0"
    assert len([p for p in pins.files if p.target.startswith("upstream/")]) == 31
    assert all(not p.target.endswith(("app.py", "model_helper.py")) for p in pins.files)


def fixture_recipe(tmp_path):
    module = api()
    pins = module.load_yourmt3_pins().model_copy(deep=True)
    inputs = []
    for i, pin in enumerate(pins.wheels):
        name = f"fixture{i}/LICENSE"
        path = tmp_path / pin.filename
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(name, f"original license{i}".encode())
            archive.writestr(f"fixture{i}/module.py", f"VALUE = {i}\n".encode())
        identity = capture_stream_input(path)
        pin.size_bytes, pin.sha256 = identity.size_bytes, identity.sha256
        pin.notices = {name: hashlib.sha256(f"original license{i}".encode()).hexdigest()}
        pin.omitted_members = {}
        inputs.append(identity)
    pins.files = []
    return module, pins, inputs


def test_complete_recipe_is_exclusive_and_rejects_changed_archive(tmp_path):
    module, pins, inputs = fixture_recipe(tmp_path)
    dest = tmp_path / "payload"
    expected = module.yourmt3_payload(pins, inputs)
    assert len(expected) == 118
    assert module.yourmt3_payload(pins, inputs, dest) == expected
    with pytest.raises(FileExistsError):
        module.yourmt3_payload(pins, inputs, dest)
    with inputs[-1].path.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(OfflineError, match="changed"):
        module.yourmt3_payload(pins, inputs)


def test_missing_artifacts_and_unlicensed_payload_fail_before_publication(tmp_path):
    module, pins, inputs = fixture_recipe(tmp_path)
    with pytest.raises(ValueError, match="complete|count"):
        module.yourmt3_payload(pins, inputs[:-1])
    pins.wheels[0].notices = {"missing/LICENSE": "0" * 64}
    with pytest.raises(ValueError, match="notice"):
        module.yourmt3_payload(pins, inputs)


def test_case_collisions_and_implicit_startup_hooks_are_rejected(tmp_path):
    module, pins, inputs = fixture_recipe(tmp_path)
    path = inputs[1].path
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fixture0/LICENSE", b"duplicate")
    inputs[1] = capture_stream_input(path)
    pins.wheels[1].size_bytes = inputs[1].size_bytes
    pins.wheels[1].sha256 = inputs[1].sha256
    pins.wheels[1].notices = {"fixture0/LICENSE": hashlib.sha256(b"duplicate").hexdigest()}
    with pytest.raises(ValueError, match="collid"):
        module.yourmt3_payload(pins, inputs)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("autorun.pth", b"import injected")
    inputs[1] = capture_stream_input(path)
    pins.wheels[1].size_bytes = inputs[1].size_bytes
    pins.wheels[1].sha256 = inputs[1].sha256
    with pytest.raises(ValueError, match="Unsafe"):
        module.yourmt3_payload(pins, inputs)
