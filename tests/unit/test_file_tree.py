"""A bounded immutable tree pass rejects file/directory changes and linked payloads."""

from pathlib import Path

import pytest

from suno2flp.core.file_tree import capture_file_tree
from suno2flp.core.offline_files import capture_stream_input


def test_tree_retains_every_current_file_identity(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    a = tmp_path / "pkg/a.py"
    b = tmp_path / "LICENSE"
    a.write_bytes(b"code")
    b.write_bytes(b"notice")
    assert capture_file_tree(tmp_path) == sorted(
        [capture_stream_input(a), capture_stream_input(b)], key=lambda i: i.path
    )
    with pytest.raises(ValueError, match="budget"):
        capture_file_tree(tmp_path, max_files=1)
    with pytest.raises(ValueError, match="budget"):
        capture_file_tree(tmp_path, max_bytes=2)


def test_tree_change_during_a_callback_fails(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b"code")
    calls = 0

    def mutate():
        nonlocal calls
        calls += 1
        if calls == 2:
            (tmp_path / "extra.py").write_bytes(b"new")
        return False

    with pytest.raises(ValueError, match="changed"):
        capture_file_tree(tmp_path, should_cancel=mutate)


def test_tree_cancellation_and_links_fail(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_bytes(b"code")
    with pytest.raises(Exception, match="cancelled"):
        capture_file_tree(tmp_path, should_cancel=lambda: True)
    try:
        (tmp_path / "linked.py").symlink_to(tmp_path / "a.py")
    except OSError:
        pytest.skip("OS does not permit symbolic-link creation for this user")
    with pytest.raises(Exception, match="[Ll]ink|[Rr]eparse"):
        capture_file_tree(tmp_path)
