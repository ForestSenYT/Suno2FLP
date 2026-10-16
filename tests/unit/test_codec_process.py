"""Real authored child processes prove bounded background lifetime and output handling."""

import sys
from threading import Event, Timer

import pytest

from suno2flp.core.errors import OfflineError


def run(code, **kwargs):
    from suno2flp.integrations.codec_process import run_bounded_process

    return run_bounded_process([sys.executable, "-I", "-S", "-B", "-c", code], **kwargs)


def test_success_preserves_complete_stdout_and_stderr_without_a_shell():
    stdout, stderr = run("import sys; print('actual'); print('diagnostic', file=sys.stderr)")
    assert stdout.strip() == b"actual" and stderr.strip() == b"diagnostic"


def test_nonzero_child_result_is_an_explicit_failure():
    with pytest.raises(OfflineError) as error:
        run("raise SystemExit(7)")
    assert error.value.code == "audio_worker_failed"


def test_owned_child_timeout_and_cooperative_cancellation_are_bounded():
    with pytest.raises(OfflineError) as error:
        run("import time; time.sleep(30)", timeout=0.1)
    assert error.value.code == "audio_worker_timeout"
    requested = Event()
    timer = Timer(0.1, requested.set)
    timer.start()
    try:
        with pytest.raises(OfflineError) as error:
            run("import time; time.sleep(30)", should_cancel=requested.is_set)
        assert error.value.code == "user_cancelled"
    finally:
        timer.cancel()


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_noisy_child_cannot_allocate_unbounded_parent_output(stream):
    with pytest.raises(OfflineError) as error:
        run(f"import sys; sys.{stream}.write('x'*2000000)", max_bytes=4096)
    assert error.value.code == "audio_worker_output_limit"


def test_cancellation_keeps_diagnostics_emitted_before_the_request(tmp_path):
    marker = tmp_path / "ready"
    code = (
        "import sys,time; from pathlib import Path; "
        "print('before cancellation',flush=True); "
        "print('native diagnostic',file=sys.stderr,flush=True); "
        f"Path({str(marker)!r}).write_text('ready'); time.sleep(30)"
    )
    with pytest.raises(OfflineError) as error:
        run(code, should_cancel=marker.exists)
    assert error.value.code == "user_cancelled"
    assert error.value.stdout.splitlines() == [b"before cancellation"]
    assert error.value.stderr.splitlines() == [b"native diagnostic"]
