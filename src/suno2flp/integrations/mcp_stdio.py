"""Opt-in newline JSON-RPC stdio transport restricted to discovery methods."""

import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import TextIO

from pydantic import JsonValue, TypeAdapter

from suno2flp.core.errors import IntegrationUnavailableError
from suno2flp.core.offline_files import load_unique_json


class StdioMcpTransport:
    """Caller supplies an audited startup command; no implicit backend/host launch."""

    def __init__(self, command: list[str], *, timeout: float = 10, cwd: Path | None = None):
        if not command or any(not isinstance(item, str) or not item for item in command):
            raise IntegrationUnavailableError("An explicit nonempty argv list is required")
        if not 0.05 <= timeout <= 60:
            raise IntegrationUnavailableError("Timeout must be 0.05..60 seconds")
        self.timeout = timeout
        self.closed = False
        self._id = 0
        self._failure: Exception | None = None
        self._writer: threading.Thread | None = None
        self._lines: queue.Queue[str | None] = queue.Queue(maxsize=128)
        self._process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            bufsize=1,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert self._process.stdout is not None and self._process.stderr is not None
        self._reader = threading.Thread(
            target=self._read, args=(self._process.stdout,), daemon=True
        )
        self._stderr = threading.Thread(
            target=self._drain, args=(self._process.stderr,), daemon=True
        )
        self._reader.start()
        self._stderr.start()

    def _read(self, stream: TextIO) -> None:
        try:
            while not self.closed:
                line = stream.readline(1024 * 1024 + 1)
                if len(line) > 1024 * 1024:
                    raise ValueError("MCP frame exceeds 1 MiB")
                self._lines.put_nowait(line if line else None)
                if not line:
                    break
        except Exception as exc:
            self._failure = exc

    def _drain(self, stream: TextIO) -> None:
        try:
            while stream.read(4096):
                pass  # stderr is diagnostic, never protocol input or an instruction.
        except (OSError, UnicodeError, ValueError):
            pass

    def _send(self, message: dict[str, JsonValue], timeout: float | None = None) -> None:
        if self.closed or self._process.stdin is None:
            raise IntegrationUnavailableError("MCP transport is closed")
        text = json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n"
        if len(text.encode()) > 1024 * 1024:
            raise IntegrationUnavailableError("MCP outgoing frame exceeds 1 MiB")
        done = threading.Event()
        errors: list[Exception] = []

        def write() -> None:
            try:
                assert self._process.stdin is not None
                self._process.stdin.write(text)
                self._process.stdin.flush()
            except Exception as exc:
                errors.append(exc)
            finally:
                done.set()

        self._writer = threading.Thread(target=write, daemon=True)
        self._writer.start()
        if not done.wait(self.timeout if timeout is None else timeout):
            self.close(force=True)
            raise IntegrationUnavailableError("MCP write timed out")
        if errors:
            raise IntegrationUnavailableError(f"MCP write failed: {errors[0]}")
        self._writer.join(timeout=0.2)

    def notify(self, method: str, params: dict[str, JsonValue]) -> None:
        if method not in {"notifications/initialized", "notifications/cancelled"}:
            raise IntegrationUnavailableError("Only MCP lifecycle notifications are allowed")
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if method not in {"initialize", "tools/list", "ping"}:
            raise IntegrationUnavailableError("Only discovery requests are allowed; no tools/call")
        self._id += 1
        request_id = self._id
        deadline = time.monotonic() + self.timeout
        try:
            self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            for _ in range(256):
                if self._failure is not None:
                    raise ValueError(f"MCP reader failed: {self._failure}")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty
                line = self._lines.get(timeout=remaining)
                if line is None:
                    raise ValueError("MCP server closed stdout")
                message = load_unique_json(line.encode())
                json.dumps(message, allow_nan=False)
                if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                    raise ValueError("Invalid JSON-RPC envelope")
                if "method" in message:
                    if message["method"] == "ping" and "id" in message:
                        self._send({"jsonrpc": "2.0", "id": message["id"], "result": {}})
                    elif "id" in message:
                        raise ValueError("Unnegotiated server request")
                    continue  # Notifications are data; capability queries always refresh inventory.
                if type(message.get("id")) is not int or message["id"] != request_id:
                    raise ValueError("Mismatched JSON-RPC response id")
                if "error" in message or not isinstance(message.get("result"), dict):
                    raise ValueError(
                        f"MCP request failed: {message.get('error', 'missing result')}"
                    )
                return TypeAdapter(dict[str, JsonValue]).validate_python(message["result"])
            raise ValueError("Too many messages before MCP response")
        except queue.Empty as exc:
            try:
                self._send(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/cancelled",
                        "params": {"requestId": request_id, "reason": "timeout"},
                    },
                    timeout=0.1,
                )
            finally:
                self.close(force=True)
            raise IntegrationUnavailableError("MCP request timed out") from exc
        except (OSError, ValueError, RuntimeError, IntegrationUnavailableError) as exc:
            self.close(force=True)
            raise IntegrationUnavailableError(f"MCP transport failed: {exc}") from exc

    def close(self, *, force: bool = False) -> None:
        if self.closed:
            return
        self.closed = True
        if force and self._process.poll() is None:
            self._process.terminate()
        if self._writer is not None:
            self._writer.join(timeout=0.2)
        if self._process.stdin is not None and not (self._writer and self._writer.is_alive()):
            try:
                self._process.stdin.close()
            except (OSError, ValueError):
                pass
        try:
            self._process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1)
        self._reader.join(timeout=0.2)
        self._stderr.join(timeout=0.2)
        for stream, thread in (
            (self._process.stdout, self._reader),
            (self._process.stderr, self._stderr),
        ):
            if stream is not None and not thread.is_alive():
                stream.close()
