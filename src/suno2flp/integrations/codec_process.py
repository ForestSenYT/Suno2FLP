"""Bounded background calls with captured diagnostics; only the owned child is stopped."""

import os
import subprocess
import threading
import time
from collections.abc import Callable
from typing import BinaryIO

from suno2flp.core.audio_decode import DecodeCancelled
from suno2flp.core.codec_backend import CodecCancelled, CodecProcessError


def run_bounded_process(
    arguments: list[str],
    *,
    should_cancel: Callable[[], bool] | None = None,
    timeout: float = 300,
    max_bytes: int = 1024**2,
) -> tuple[bytes, bytes]:
    if timeout <= 0 or max_bytes <= 0:
        raise ValueError("Process limits must be positive")
    if should_cancel is not None and should_cancel():
        raise DecodeCancelled()
    environment = {
        key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ
    }
    environment.update(
        OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1"
    )
    deadline = time.monotonic() + timeout
    output: list[bytes] = []
    errors: list[bytes] = []
    limit = threading.Event()
    lock = threading.Lock()
    length = 0
    read_errors: list[OSError] = []

    def read(stream: BinaryIO, destination: list[bytes]) -> None:
        nonlocal length
        try:
            while block := stream.read(4096):
                with lock:
                    remaining = max(0, max_bytes - length)
                    destination.append(block[:remaining])
                    length += len(block)
                    if length > max_bytes:
                        limit.set()
                        break
        except OSError as error:
            read_errors.append(error)

    try:
        child = subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as error:
        raise CodecProcessError("audio_worker_unavailable", str(error)) from error
    assert child.stdout is not None and child.stderr is not None
    readers = [
        threading.Thread(target=read, args=(child.stdout, output), daemon=True),
        threading.Thread(target=read, args=(child.stderr, errors), daemon=True),
    ]
    failure: str | None = None
    for reader in readers:
        reader.start()
    try:
        while child.poll() is None:
            if limit.is_set():
                failure = "audio_worker_output_limit"
                break
            if should_cancel is not None and should_cancel():
                failure = "user_cancelled"
                break
            if time.monotonic() > deadline:
                failure = "audio_worker_timeout"
                break
            time.sleep(0.01)
    finally:
        if child.poll() is None:
            child.kill()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired as error:
            raise CodecProcessError(
                "audio_worker_cleanup_failed", f"Owned process {child.pid} did not exit"
            ) from error
        for reader in readers:
            reader.join(timeout=2)
        if any(reader.is_alive() for reader in readers):
            raise CodecProcessError("audio_worker_cleanup_failed", "Owned child pipe did not close")
        child.stdout.close()
        child.stderr.close()
    stdout, stderr = b"".join(output), b"".join(errors)
    if limit.is_set():
        failure = "audio_worker_output_limit"
    if failure == "user_cancelled":
        raise CodecCancelled(stdout, stderr)
    if failure:
        raise CodecProcessError(
            failure, "Audio child stopped at its configured limit", stdout, stderr
        )
    if read_errors or child.returncode:
        raise CodecProcessError(
            "audio_worker_failed",
            f"Audio child exit {child.returncode}; {stderr[:4096].decode('utf-8', 'replace')}",
            stdout,
            stderr,
        )
    return stdout, stderr
