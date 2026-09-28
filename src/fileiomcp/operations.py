"""Filesystem operations exposed by the standalone fileio MCP server."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any


class FileOperationError(ValueError):
    """An invalid or unsuccessful filesystem operation."""


def _atomic_text_write(target: Path, content: str, encoding: str, *, overwrite: bool) -> None:
    if target.is_symlink():
        raise FileOperationError(f"Use the real file path rather than a symbolic link: {target}")
    # Encode before opening anything: codec errors must never truncate the target.
    payload = content.encode(encoding)
    descriptor, staging = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            if target.is_file():
                shutil.copymode(target, staging)
            os.replace(staging, target)
        else:
            # Exclusive publication prevents a racing create from being overwritten.
            os.link(staging, target)
    finally:
        Path(staging).unlink(missing_ok=True)


def _text_lines(text: str) -> list[str]:
    # Unlike splitlines(), vertical tabs and Unicode separators stay inside lines.
    parts = re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text)
    if parts and not parts[-1]:
        parts.pop()
    return parts


def _path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise FileOperationError(f"{field} must be a non-empty path string")
    return Path(value).expanduser()


def _require_kind(path: Path, *, directory: bool) -> None:
    if not path.exists():
        raise FileOperationError(f"Path does not exist: {path}")
    if directory and not path.is_dir():
        raise FileOperationError(f"Expected a directory: {path}")
    if not directory and not path.is_file():
        raise FileOperationError(f"Expected a file: {path}")


def _check_destination(path: Path, *, directory: bool, overwrite: bool) -> None:
    if path.is_symlink():
        raise FileOperationError(f"Use the real destination rather than a symbolic link: {path}")
    if not path.exists():
        return
    if not overwrite:
        raise FileOperationError(f"Destination already exists: {path}; set overwrite=true to replace it")
    if directory:
        if not path.is_dir():
            raise FileOperationError(f"Cannot replace a non-directory with a directory: {path}")
    else:
        if not path.is_file():
            raise FileOperationError(f"Cannot replace a non-file with a file: {path}")


def _staged_directory_copy(src: Path, dst: Path, overwrite: bool) -> str | None:
    _check_destination(dst, directory=True, overwrite=overwrite)
    dst.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{dst.name}.", dir=dst.parent))
    new, previous = staging / "new", staging / "previous"
    try:
        shutil.copytree(src, new)
        if dst.exists():
            _check_destination(dst, directory=True, overwrite=overwrite)
            dst.rename(previous)
        try:
            new.rename(dst)
        except OSError:
            if previous.exists():
                previous.rename(dst)
            raise
        if previous.exists():
            try:
                shutil.rmtree(previous)
            except OSError:
                return str(previous)
        return None
    finally:
        # Never delete a recovery backup when publication/rollback/cleanup fails.
        if not previous.exists():
            shutil.rmtree(staging, ignore_errors=True)


def directory_create(path: str, parents: bool = False, exist_ok: bool = False) -> dict[str, Any]:
    target = _path(path, "path")
    target.mkdir(parents=parents, exist_ok=exist_ok)
    return {"operation": "directory_create", "path": str(target), "created": True}


def directory_delete(path: str, recursive: bool = False) -> dict[str, Any]:
    target = _path(path, "path")
    _require_kind(target, directory=True)
    if recursive:
        shutil.rmtree(target)
    else:
        target.rmdir()
    return {"operation": "directory_delete", "path": str(target), "deleted": True}


def directory_move(source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
    src, dst = _path(source, "source"), _path(destination, "destination")
    _require_kind(src, directory=True)
    if src.resolve() == dst.resolve() or src.resolve() in dst.resolve().parents or dst.resolve() in src.resolve().parents:
        raise FileOperationError("Source and destination directories cannot contain one another")
    if src.is_symlink():
        raise FileOperationError("Move the real directory rather than a symbolic link")
    backup = _staged_directory_copy(src, dst, overwrite)
    shutil.rmtree(src)
    return {"operation": "directory_move", "source": str(src), "destination": str(dst), "moved": True, "backup_path": backup}


def directory_copy(source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
    src, dst = _path(source, "source"), _path(destination, "destination")
    _require_kind(src, directory=True)
    if src.resolve() == dst.resolve() or src.resolve() in dst.resolve().parents or dst.resolve() in src.resolve().parents:
        raise FileOperationError("Source and destination directories cannot contain one another")
    backup = _staged_directory_copy(src, dst, overwrite)
    return {"operation": "directory_copy", "source": str(src), "destination": str(dst), "copied": True, "backup_path": backup}


def file_create(path: str, content: str = "", create_parents: bool = False, overwrite: bool = False, encoding: str = "utf-8") -> dict[str, Any]:
    target = _path(path, "path")
    if not isinstance(content, str):
        raise FileOperationError("content must be a string")
    if target.exists() and not overwrite:
        if target.is_file() and target.read_bytes() == content.encode(encoding):
            return {"operation": "file_create", "path": str(target), "bytes": target.stat().st_size, "already_present": True}
        raise FileOperationError(f"File already exists: {target}; inspect it with file_read, then set overwrite=true only if replacement is intended")
    if target.exists() and not target.is_file():
        raise FileOperationError(f"Expected a file path: {target}")
    if create_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_text_write(target, content, encoding, overwrite=overwrite)
    return {"operation": "file_create", "path": str(target), "bytes": target.stat().st_size}


def file_append(path: str, content: str, encoding: str = "utf-8") -> dict[str, Any]:
    """Append a short text chunk so clients can write large documents in valid, small tool calls."""
    target = _path(path, "path")
    _require_kind(target, directory=False)
    if not isinstance(content, str) or not content:
        raise FileOperationError("content must be a non-empty string")
    with target.open("r", encoding=encoding, newline="") as stream:
        original = stream.read()
    _atomic_text_write(target, original + content, encoding, overwrite=True)
    return {"operation": "file_append", "path": str(target), "appended_characters": len(content), "bytes": target.stat().st_size}


def file_read(path: str, start_line: int = 1, end_line: int | None = None, encoding: str = "utf-8") -> dict[str, Any]:
    target = _path(path, "path")
    _require_kind(target, directory=False)
    if isinstance(start_line, bool) or not isinstance(start_line, int) or start_line < 1:
        raise FileOperationError("start_line must be a positive integer")
    if end_line is not None and (isinstance(end_line, bool) or not isinstance(end_line, int) or end_line < start_line):
        raise FileOperationError("end_line must be an integer at least start_line")
    payload = target.read_bytes()
    parts = _text_lines(payload.decode(encoding))
    last = min(end_line if end_line is not None else start_line + 199, len(parts))
    return {"operation": "file_read", "path": str(target), "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(), "line_count": len(parts),
            "lines": [{"line": i + 1, "text": parts[i].rstrip("\r\n")} for i in range(start_line - 1, last)]}


def file_delete(path: str) -> dict[str, Any]:
    target = _path(path, "path")
    _require_kind(target, directory=False)
    target.unlink()
    return {"operation": "file_delete", "path": str(target), "deleted": True}


def file_move(source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
    src, dst = _path(source, "source"), _path(destination, "destination")
    _require_kind(src, directory=False)
    if src.resolve() == dst.resolve():
        raise FileOperationError("Source and destination are the same file")
    if src.is_symlink():
        raise FileOperationError("Move the real file rather than a symbolic link")
    file_copy(source, destination, overwrite)
    src.unlink()
    return {"operation": "file_move", "source": str(src), "destination": str(dst), "moved": True}


def file_copy(source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
    src, dst = _path(source, "source"), _path(destination, "destination")
    _require_kind(src, directory=False)
    if src.resolve() == dst.resolve():
        raise FileOperationError("Source and destination are the same file")
    if dst.exists() and src.samefile(dst):
        raise FileOperationError("Source and destination refer to the same file")
    _check_destination(dst, directory=False, overwrite=overwrite)
    dst.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=dst.parent)
    os.close(descriptor)
    try:
        shutil.copy2(src, staging)
        if overwrite:
            os.replace(staging, dst)
        else:
            os.link(staging, dst)
    finally:
        Path(staging).unlink(missing_ok=True)
    return {"operation": "file_copy", "source": str(src), "destination": str(dst), "copied": True}


def file_edit_lines(
    path: str,
    operation: str,
    start_line: int,
    end_line: int | None = None,
    lines: list[str] | None = None,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    """Apply a 1-based inclusive delete/replace range or insert after a line (0 means before line 1)."""
    target = _path(path, "path")
    _require_kind(target, directory=False)
    if operation not in {"delete", "replace", "insert_after"}:
        raise FileOperationError("operation must be delete, replace, or insert_after")
    if isinstance(start_line, bool) or not isinstance(start_line, int) or start_line < 0:
        raise FileOperationError("start_line must be a non-negative integer")
    if lines is None:
        lines = []
    if not isinstance(lines, list) or any(not isinstance(line, str) or "\n" in line or "\r" in line for line in lines):
        raise FileOperationError("lines must be an array of strings without line breaks")
    if operation in {"delete", "replace"}:
        if start_line < 1 or isinstance(end_line, bool) or not isinstance(end_line, int) or end_line < start_line:
            raise FileOperationError("delete and replace require a valid 1-based inclusive start_line/end_line range")
        if operation == "delete" and lines:
            raise FileOperationError("lines must be empty for delete")
        if operation == "replace" and not lines:
            raise FileOperationError("replace requires at least one line; use delete to remove a range")
    elif end_line is not None:
        raise FileOperationError("end_line is only valid for delete and replace")

    with target.open("r", encoding=encoding, newline="") as stream:
        original = stream.read()
    match = re.search(r"\r\n|\n|\r", original)
    newline = match.group() if match else "\n"
    had_final_newline = original.endswith(("\n", "\r"))
    content_lines = _text_lines(original)
    if operation in {"delete", "replace"}:
        if end_line > len(content_lines):
            raise FileOperationError(f"end_line exceeds file line count ({len(content_lines)})")
        first, last = start_line - 1, end_line
    else:
        if start_line > len(content_lines):
            raise FileOperationError(f"start_line exceeds file line count ({len(content_lines)}); use 0 to insert at the beginning")
        first = last = start_line
    prefix, suffix = "".join(content_lines[:first]), "".join(content_lines[last:])
    replacement = newline.join(lines)
    if lines and (suffix or had_final_newline):
        replacement += newline
    if operation == "insert_after" and lines and prefix and not prefix.endswith(("\r", "\n")):
        prefix += newline
    updated = prefix + replacement + suffix
    _atomic_text_write(target, updated, encoding, overwrite=True)
    return {
        "operation": f"file_edit_lines_{operation}", "path": str(target),
        "line_count_before": len(content_lines), "line_count_after": len(_text_lines(updated)),
    }


OPERATIONS = {
    "directory_create": directory_create,
    "directory_delete": directory_delete,
    "directory_move": directory_move,
    "directory_copy": directory_copy,
    "file_create": file_create,
    "file_append": file_append,
    "file_read": file_read,
    "file_delete": file_delete,
    "file_move": file_move,
    "file_copy": file_copy,
    "file_edit_lines": file_edit_lines,
}
