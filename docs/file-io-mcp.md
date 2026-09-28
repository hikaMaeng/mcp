# File I/O MCP

`fileiomcp` is a separate stdio MCP server for filesystem operations, with its own command, server identity, and tool set. The server version is `0.2.0`. Reconnect the MCP client after changing the implementation to load its new version and tool schemas.

```powershell
uv sync --locked
uv run --frozen fileiomcp
```

Register the command above as a separate stdio MCP server in the MCP client. Standard output is reserved for MCP protocol traffic; diagnostics go to standard error.

## Tools

| Tool | Behavior |
|---|---|
| `file_read` | Read numbered lines (default: up to 200) and return the file's SHA-256. |
| `directory_create` | Create a directory; optionally create parents or accept an existing directory. |
| `directory_delete` | Delete an empty directory, or delete a tree with `recursive=true`. |
| `directory_move` / `directory_copy` | Move or copy a directory tree to the exact destination path. |
| `file_create` / `file_append` / `file_delete` | Create/replace UTF-8 text, append text chunks, or delete a file. |
| `file_move` / `file_copy` | Move or copy a file to the exact destination path. |
| `file_edit_lines` | Delete or replace a 1-based inclusive range, or insert lines after a 1-based line. Use line `0` to insert at the beginning. |

Move/copy operations reject an existing destination unless `overwrite=true`. `file_create` accepts a retry with identical content; differing existing content requires explicit `overwrite=true`. Inspect it with `file_read` before replacing it.

`file_create`, `file_append`, and `file_edit_lines` encode and write a sibling temporary file before publishing it. Encoding or publication failures preserve the existing file. File copies also stage the complete content before replacing the destination. Directory copies keep the old destination recoverable during publication; a cleanup failure can return a retained `backup_path`. Moves publish the destination before removing the source, so cleanup errors can leave both paths. These steps are not a transaction across independent filesystem processes.

Writes through symbolic links are rejected. Exclusive file publication requires filesystem hard-link support (available on NTFS).

Text content has no server length limit. `file_append` allows incremental writing, but each successful chunk is already committed. The MCP client must permit enough output tokens to complete its JSON arguments; truncated JSON is rejected by the client before this server receives it.

Line edits use 1-based inclusive ranges. Each `lines` item is a logical line without CR or LF; deletion requires no `lines`, replacement requires at least one line. Untouched lines preserve their original newline bytes, including mixed LF/CRLF. Inserted lines use the first detected newline convention. A replaced block retains a terminating newline when another line follows or the original file ended with a newline.

Regression checks: `uv run --frozen pytest tests/test_fileio.py -q`. The optional `scripts/fileio_live_check.py` exercises real stdio calls with the loaded `mimo-lmstudio-dflash` model through `http://127.0.0.1:12345`; it writes only inside its temporary directory and saves results to `artifacts/fileio-live-check.json`.

All paths are interpreted by the server process. Recursive deletion permanently removes the selected directory tree, so specify its path deliberately.
