"""Standalone read-only Windows Core Audio discovery; never activate a stream."""

import ctypes
import hashlib
import json
import platform
import sys
import sysconfig
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol


class AudioAPI(Protocol):
    def endpoints(self) -> list[dict[str, Any]]: ...
    def default(self, role: int) -> dict[str, Any]: ...


def require_runtime() -> None:
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ValueError("Windows audio worker requires -I -S -B")
    if sys.platform != "win32" or sysconfig.get_platform() != "win-amd64":
        raise ValueError("Windows x64 Core Audio discovery only")
    if platform.python_implementation() != "CPython" or sysconfig.get_config_var("Py_GIL_DISABLED"):
        raise ValueError("Use the inspected ordinary CPython ABI")
    if {(3, 11): "3.11.16", (3, 14): "3.14.7"}.get(
        sys.version_info[:2]
    ) != platform.python_version():
        raise ValueError("Use the inspected application Python3.11.16 or3.14.7")


def collect_observation(api: AudioAPI) -> dict[str, Any]:
    started = time.time_ns()
    endpoints = api.endpoints()
    defaults = [api.default(role) for role in range(3)]
    return {
        "protocol": "windows-render-endpoints-v1",
        "started_ns": started,
        "finished_ns": time.time_ns(),
        "os_version": platform.version(),
        "endpoints": endpoints,
        "defaults": defaults,
    }


def _bind(module: Any, name: str, arguments: list[Any], result: Any) -> Any:
    function = getattr(module, name)
    function.argtypes, function.restype = arguments, result
    return function


def _method(pointer: Any, index: int, *arguments: Any) -> Any:
    if sys.platform != "win32":
        raise ValueError("Windows COM interfaces are unavailable on this platform")
    if not pointer.value:
        raise ValueError("Native API returned a null COM interface")
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, *arguments)(table[index])


def _check(result: int, stage: str) -> None:
    if result != 0:
        raise OSError(f"{stage}: HRESULT0x{result & 0xFFFFFFFF:08x}")


def _guid(value: str) -> Any:
    return (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)


def _release(pointer: Any) -> None:
    if pointer.value:
        _method(pointer, 2)(pointer)
        pointer.value = None


class _NativeAudio:
    kernel: Any
    ole: Any
    enumerator: ctypes.c_void_p
    initialized: bool

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise ValueError("Windows COM discovery is unavailable on this platform")
        load = ctypes.WinDLL
        self.kernel = load("kernel32.dll", use_last_error=True)
        self.ole = load("ole32.dll", use_last_error=True)
        self.enumerator = ctypes.c_void_p()
        self.initialized = False
        _bind(self.ole, "CoInitializeEx", [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_int32)
        _bind(self.ole, "CoUninitialize", [], None)
        _bind(self.ole, "CoTaskMemFree", [ctypes.c_void_p], None)
        _bind(
            self.ole,
            "CoCreateInstance",
            [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            ],
            ctypes.c_int32,
        )
        result = self.ole.CoInitializeEx(None, 0)
        if result not in (0, 1):
            _check(result, "CoInitializeEx")
        self.initialized = True
        try:
            clsid = _guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
            iid = _guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
            _check(
                self.ole.CoCreateInstance(
                    ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(self.enumerator)
                ),
                "CoCreateInstance",
            )
            if not self.enumerator.value:
                raise ValueError("No IMMDeviceEnumerator interface")
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        try:
            _release(self.enumerator)
        finally:
            if self.initialized:
                self.initialized = False
                self.ole.CoUninitialize()

    def _device(self, device: Any) -> dict[str, Any]:
        text, state = ctypes.c_void_p(), ctypes.c_uint32()
        try:
            _check(
                _method(device, 5, ctypes.POINTER(ctypes.c_void_p))(device, ctypes.byref(text)),
                "GetId",
            )
            if not text.value:
                raise ValueError("GetId returned no endpoint ID")
            _check(
                _method(device, 6, ctypes.POINTER(ctypes.c_uint32))(device, ctypes.byref(state)),
                "GetState",
            )
            return {"id": ctypes.wstring_at(text.value), "state": state.value}
        finally:
            if text.value:
                self.ole.CoTaskMemFree(text)

    def endpoints(self) -> list[dict[str, Any]]:
        collection = ctypes.c_void_p()
        try:
            _check(
                _method(
                    self.enumerator,
                    3,
                    ctypes.c_int32,
                    ctypes.c_uint32,
                    ctypes.POINTER(ctypes.c_void_p),
                )(self.enumerator, 0, 15, ctypes.byref(collection)),
                "EnumAudioEndpoints",
            )
            count = ctypes.c_uint32()
            _check(
                _method(collection, 3, ctypes.POINTER(ctypes.c_uint32))(
                    collection, ctypes.byref(count)
                ),
                "GetCount",
            )
            if count.value > 256:
                raise ValueError("Endpoint observation exceeds256devices; no truncation")
            result = []
            for index in range(count.value):
                device = ctypes.c_void_p()
                try:
                    _check(
                        _method(collection, 4, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p))(
                            collection, index, ctypes.byref(device)
                        ),
                        "Item",
                    )
                    result.append(self._device(device))
                finally:
                    _release(device)
            return result
        finally:
            _release(collection)

    def default(self, role: int) -> dict[str, Any]:
        device = ctypes.c_void_p()
        try:
            hr = _method(
                self.enumerator, 4, ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_void_p)
            )(self.enumerator, 0, role, ctypes.byref(device))
            if hr & 0xFFFFFFFF == 0x80070490:
                if device.value:
                    raise ValueError("E_NOTFOUND returned an unexpected endpoint pointer")
                return {"role": role, "hresult": 0x80070490, "device_id": None}
            _check(hr, "GetDefaultAudioEndpoint")
            data = self._device(device)
            if data["state"] != 1:
                raise ValueError("Default endpoint is not active; snapshot cannot be accepted")
            return {"role": role, "hresult": 0, "device_id": data["id"]}
        finally:
            _release(device)

    def libraries(self) -> tuple[Path, list[dict[str, Any]]]:
        _bind(
            self.kernel,
            "GetWindowsDirectoryW",
            [ctypes.c_wchar_p, ctypes.c_uint32],
            ctypes.c_uint32,
        )
        _bind(self.kernel, "GetModuleHandleW", [ctypes.c_wchar_p], ctypes.c_void_p)
        _bind(
            self.kernel,
            "GetModuleFileNameW",
            [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32],
            ctypes.c_uint32,
        )
        buffer = ctypes.create_unicode_buffer(32768)
        count = self.kernel.GetWindowsDirectoryW(buffer, len(buffer))
        if not 0 < count < len(buffer):
            raise ValueError("Windows directory unavailable or truncated")
        windows = Path(buffer.value).resolve()
        libraries = []
        for name in ("kernel32.dll", "ole32.dll", "MMDevApi.dll"):
            handle = self.kernel.GetModuleHandleW(name)
            if not handle:
                raise ValueError(f"Selected API module not loaded: {name}")
            count = self.kernel.GetModuleFileNameW(handle, buffer, len(buffer))
            if not 0 < count < len(buffer):
                raise ValueError("Selected API module path unavailable or truncated")
            path = Path(buffer.value).resolve()
            if path != (windows / "System32" / name).resolve():
                raise ValueError("Selected API module is not the Windows system library")
            before = path.stat()
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            after = path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ValueError("Selected API library changed while hashing")
            libraries.append(
                dict(
                    path=str(path),
                    sha256=digest,
                    size_bytes=after.st_size,
                    mtime_ns=after.st_mtime_ns,
                )
            )
        return windows, libraries


@contextmanager
def _native() -> Iterator[_NativeAudio]:
    api = _NativeAudio()
    try:
        yield api
    finally:
        api.close()


def main() -> None:
    require_runtime()
    if len(sys.argv) != 1:
        raise ValueError("Discovery worker accepts no operations or device-change arguments")
    with _native() as api:
        facts = collect_observation(api)
        windows, libraries = api.libraries()
    result = dict(
        protocol="windows-audio-worker-v1",
        facts=facts,
        python_version=platform.python_version(),
        python_abi=f"cp{sys.version_info.major}{sys.version_info.minor}",
        isolated=bool(sys.flags.isolated),
        no_site=bool(sys.flags.no_site),
        no_bytecode=sys.dont_write_bytecode,
        pointer_bits=ctypes.sizeof(ctypes.c_void_p) * 8,
        windows_directory=str(windows),
        libraries=libraries,
        stream_activation_calls=0,
        device_mutation_calls=0,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
