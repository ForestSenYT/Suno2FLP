"""Fixed local TensorFlow graph probe in a private -I -S -B Windows CPU process."""

import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import sys
import sysconfig
from pathlib import Path
from typing import Any

STEMS = ("vocals", "drums", "bass", "other")
FIXTURES = {"silence": 1025, "impulses": 12347, "stereo-pattern": 44117}


def isolate_environment(packages: Path, attempt: Path) -> None:
    if any(name in str(packages).casefold() for name in ("site-packages", "dist-packages")):
        raise ValueError("Private TensorFlow cannot run from ambient site-packages")
    os.environ.pop("TF_PLUGGABLE_DEVICE_LIBRARY_PATH", None)
    os.environ.update(
        CUDA_VISIBLE_DEVICES="-1",
        TF_USE_MODULAR_FILESYSTEM="0",
        TF_ENABLE_ONEDNN_OPTS="0",
        TF_DETERMINISTIC_OPS="1",
        TF_NUM_INTRAOP_THREADS="8",
        TF_NUM_INTEROP_THREADS="1",
        OMP_NUM_THREADS="8",
        OPENBLAS_NUM_THREADS="8",
        MKL_NUM_THREADS="8",
        NUMEXPR_NUM_THREADS="8",
        KERAS_HOME=str(attempt / "keras-cache"),
    )


def native(packages: Path, attempt: Path) -> tuple[Any, Any, Any, Any, dict[str, Any]]:
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ValueError("Worker requires -I -S -B")
    if (
        sys.platform != "win32"
        or sysconfig.get_platform() != "win-amd64"
        or platform.python_implementation() != "CPython"
        or platform.python_version() != "3.11.16"
    ):
        raise ValueError("Worker requires fixed Windows x64 CPython3.11.16")
    isolate_environment(packages, attempt)
    sys.path.insert(0, str(packages))
    np = importlib.import_module("numpy")
    tf = importlib.import_module("tensorflow")
    if tf._running_from_pip_package():
        raise ValueError("TensorFlow ambient plugin scanning must remain disabled")
    builder_module = importlib.import_module("spleeter.model")
    tf.compat.v1.disable_eager_execution()
    parameters = json.loads((packages / "spleeter/resources/4stems.json").read_text())
    parameters["MWF"] = False
    graph = tf.Graph()
    with graph.as_default():
        tf.compat.v1.set_random_seed(3)
        tf.keras.backend.set_learning_phase(0)
        waveform = tf.compat.v1.placeholder(tf.float32, shape=(None, 2), name="waveform")
        outputs = builder_module.EstimatorSpecBuilder({"waveform": waveform}, parameters).outputs
        variables = tf.compat.v1.global_variables()
        saver = tf.compat.v1.train.Saver()
    options = tf.compat.v1.ConfigProto(
        device_count={"GPU": 0}, intra_op_parallelism_threads=8, inter_op_parallelism_threads=1
    )
    session = tf.compat.v1.Session(graph=graph, config=options)
    # Never import a serialized meta graph or follow the archive's checkpoint file.
    saver.restore(session, str(packages / "model/model"))
    checkpoint_shapes = dict(tf.train.list_variables(str(packages / "model/model")))
    restored = {}
    digest = hashlib.sha256()
    for variable, value in zip(variables, session.run(variables), strict=True):
        name = variable.name.removesuffix(":0")
        shape = list(value.shape)
        if checkpoint_shapes.get(name) != shape:
            raise ValueError("Restored graph variable differs from checkpoint geometry")
        restored[name] = shape
        digest.update(name.encode() + b"\0" + str(shape).encode() + b"\0")
        digest.update(value.astype("<f4", copy=False).tobytes())
    modules = {}
    for name in ("numpy", "tensorflow", "keras", "scipy", "pandas", "spleeter", "spleeter.model"):
        module = importlib.import_module(name)
        assert module.__file__ is not None
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(packages):
            raise ValueError("Native module loaded outside fixed private payload")
        modules[name] = str(path)
    if any(name.startswith("tensorflow_io_gcs_filesystem") for name in sys.modules):
        raise ValueError("The unqualified TFIO plugin must not be loaded")
    versions = {}
    for distribution in importlib.metadata.distributions(path=[str(packages)]):
        name = distribution.metadata["Name"].lower().replace("_", "-").replace(".", "-")
        if name in versions:
            raise ValueError("Ambiguous installed native distribution")
        versions[name] = distribution.version
    probe = {
        "profile": "spleeter4-native-probe-v1",
        "device_types": [device.device_type for device in session.list_devices()],
        "intra_op_threads": session._config.intra_op_parallelism_threads,
        "inter_op_threads": session._config.inter_op_parallelism_threads,
        "versions": versions,
        "modules": modules,
        "restored_variables": restored,
        "restored_values_sha256": digest.hexdigest(),
        "repeatability_scope": "observed-two-runs-per-fixture",
        "tfio_loaded": False,
        "ambient_plugins_enabled": False,
    }
    return np, session, waveform, outputs, probe


def predict(np: Any, session: Any, waveform: Any, outputs: Any, source: Any) -> dict[str, Any]:
    result: dict[str, Any] = session.run(outputs, feed_dict={waveform: source})
    if set(result) != set(STEMS):
        raise ValueError("Native graph did not return the four fixed stems")
    for array in result.values():
        if array.shape != source.shape or array.dtype != np.float32 or not np.isfinite(array).all():
            raise ValueError("Native output shape/dtype/finite samples differ from fixed profile")
    return result


def main() -> None:
    request_path = Path(sys.argv[1]).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if set(request) != {"operation", "packages"} or request["operation"] != "probe":
        raise ValueError("Unsupported worker operation or parameters")
    attempt = request_path.parent
    np, session, waveform, outputs, probe = native(Path(request["packages"]).resolve(), attempt)
    fixtures = []
    try:
        for fixture, frames in FIXTURES.items():
            path = attempt / f"{fixture}.input.f32"
            if path.stat().st_size != frames * 8:
                raise ValueError("Probe input does not cover the fixed complete stereo signal")
            source = np.fromfile(path, dtype="<f4").reshape(frames, 2)
            if not np.isfinite(source).all():
                raise ValueError("Probe source contains nonfinite samples")
            hashes: dict[str, list[str]] = {name: [] for name in STEMS}
            for run in (1, 2):
                result = predict(np, session, waveform, outputs, source)
                for name, array in result.items():
                    raw = array.astype("<f4", copy=False).tobytes()
                    with (attempt / f"{fixture}.{name}.{run}.f32").open("xb") as stream:
                        stream.write(raw)
                    hashes[name].append(hashlib.sha256(raw).hexdigest())
            if any(pair[0] != pair[1] for pair in hashes.values()):
                raise ValueError("Observed native fixture runs are not byte repeatable")
            fixtures.append({"fixture": fixture, "frames": frames, "hashes": hashes})
    finally:
        session.close()
    probe["fixtures"] = fixtures
    with (attempt / "result.json").open("x", encoding="utf-8") as stream:
        json.dump(probe, stream, allow_nan=False, indent=2)


if __name__ == "__main__":
    main()
