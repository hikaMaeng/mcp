import asyncio
import os
import sys

import pytest
from mcp import Client, StdioServerParameters

from fileiomcp import operations as io


def test_create_retry_does_not_destroy_existing_file(tmp_path):
    path = tmp_path / "cal.html"
    content = '<html title="계산기">' + "x" * 10000 + "</html>\n"
    io.file_create(str(path), content)
    assert io.file_create(str(path), content)["already_present"]
    with pytest.raises(io.FileOperationError, match="already exists"):
        io.file_create(str(path), "different")
    assert path.read_text(encoding="utf-8") == content


def test_failed_encoding_and_publication_preserve_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "old.txt"
    path.write_bytes(b"original\r\n")
    with pytest.raises(UnicodeEncodeError):
        io.file_create(str(path), "한글", overwrite=True, encoding="ascii")
    assert path.read_bytes() == b"original\r\n"

    def reject(*args):
        raise PermissionError("simulated replace failure")

    monkeypatch.setattr(io.os, "replace", reject)
    with pytest.raises(PermissionError):
        io.file_create(str(path), "replacement", overwrite=True)
    assert path.read_bytes() == b"original\r\n"
    assert list(tmp_path.iterdir()) == [path]


def test_line_edits_preserve_untouched_mixed_endings(tmp_path):
    path = tmp_path / "mixed.txt"
    path.write_bytes(b"a\r\nb\nc")
    io.file_edit_lines(str(path), "replace", 2, 2, ["B", "C"])
    assert path.read_bytes() == b"a\r\nB\r\nC\r\nc"
    io.file_edit_lines(str(path), "delete", 2, 3)
    assert path.read_bytes() == b"a\r\nc"
    io.file_edit_lines(str(path), "insert_after", 2, lines=["tail"])
    assert path.read_bytes() == b"a\r\nc\r\ntail"
    before = path.read_bytes()
    with pytest.raises(io.FileOperationError):
        io.file_edit_lines(str(path), "delete", 1, 100)
    assert path.read_bytes() == before


def test_append_utf16_does_not_insert_additional_bom(tmp_path):
    path = tmp_path / "unicode.txt"
    io.file_create(str(path), "first\r\n", encoding="utf-16")
    io.file_append(str(path), "second\n", encoding="utf-16")
    assert path.read_bytes().decode("utf-16") == "first\r\nsecond\n"
    read = io.file_read(str(path), encoding="utf-16")
    assert read["line_count"] == 2
    assert [line["text"] for line in read["lines"]] == ["first", "second"]


def test_failed_overwrite_copy_preserves_both_files(tmp_path, monkeypatch):
    source, target = tmp_path / "source.bin", tmp_path / "target.bin"
    source.write_bytes(b"new data")
    target.write_bytes(b"old data")

    def broken_copy(src, dst):
        from pathlib import Path
        Path(dst).write_bytes(b"incomplete")
        raise OSError("simulated copy failure")

    monkeypatch.setattr(io.shutil, "copy2", broken_copy)
    with pytest.raises(OSError):
        io.file_copy(str(source), str(target), overwrite=True)
    assert source.read_bytes() == b"new data"
    assert target.read_bytes() == b"old data"
    assert len(list(tmp_path.iterdir())) == 2


def test_failed_directory_copy_and_publication_restore_destination(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "new").write_bytes(b"new")
    (target / "old").write_bytes(b"old")
    from pathlib import Path
    real_rename = Path.rename

    def reject_publication(path, dst):
        if path.name == "new" and path.parent.name.startswith(".target."):
            raise PermissionError("simulated directory publication failure")
        return real_rename(path, dst)

    monkeypatch.setattr(Path, "rename", reject_publication)
    with pytest.raises(PermissionError):
        io.directory_copy(str(source), str(target), overwrite=True)
    assert (source / "new").read_bytes() == b"new"
    assert (target / "old").read_bytes() == b"old"
    assert len(list(tmp_path.iterdir())) == 2


def test_file_and_directory_move_copy_delete_and_overlap(tmp_path):
    source = tmp_path / "source"
    io.directory_create(str(source))
    io.file_create(str(source / "a.txt"), "data")
    copied, moved = tmp_path / "copied", tmp_path / "moved"
    io.directory_copy(str(source), str(copied))
    io.directory_move(str(copied), str(moved))
    assert not copied.exists()
    io.file_move(str(moved / "a.txt"), str(moved / "b.txt"))
    assert (moved / "b.txt").read_text() == "data"
    with pytest.raises(io.FileOperationError):
        io.directory_copy(str(source), str(source / "inside"), overwrite=True)
    io.file_delete(str(moved / "b.txt"))
    io.directory_delete(str(moved))
    io.directory_delete(str(source), recursive=True)
    assert not list(tmp_path.iterdir())


def test_real_stdio_large_escaped_content_and_validation(tmp_path):
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=["-m", "fileiomcp"], env=dict(os.environ))
        async with Client(params, read_timeout_seconds=15) as client:
            tools = await client.list_tools()
            assert "file_read" in {t.name for t in tools.tools}
            path = tmp_path / "source.html"
            content = '<input title="한글">\n<script>const x = "\\quoted";</script>\n' * 200
            result = await client.call_tool("file_create", {"path": str(path), "content": content})
            assert not result.is_error, result.content
            assert path.read_bytes().decode("utf-8") == content
            # A string false must never silently enable destructive overwrite.
            bad = await client.call_tool("file_create", {"path": str(path), "content": "bad", "overwrite": "false"})
            assert bad.is_error
            assert path.read_bytes().decode("utf-8") == content
            read = await client.call_tool("file_read", {"path": str(path), "start_line": 1, "end_line": 2})
            assert not read.is_error
            assert len(read.structured_content["lines"]) == 2
    asyncio.run(exercise())
