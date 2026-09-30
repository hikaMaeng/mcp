Three independent local stdio MCP servers: web search through Codex CLI, filesystem operations, and one-shot terminal commands in a fresh process per request.

# Web Search, Filesystem & Terminal MCP

[English](README.md) | [한국어](README.ko.md)

Connect the servers you need as separate processes.

| Server | Tools | Codex CLI login |
| --- | --- | --- |
| `websearch` | Live web search with source URLs and structured summaries | Required |
| `fileiomcp` | Create, read, edit, delete, move, and copy files and directories | Not required |
| `terminalmcp` | Run a one-shot shell command in a fresh process per request | Not required |

## Prerequisites

- Python **3.11+**, [uv](https://docs.astral.sh/uv/getting-started/installation/), and Git.
- An MCP client with **stdio** server support, such as LM Studio.
- For web search: a locally installed [Codex CLI](https://developers.openai.com/codex/cli), **already logged in under the same OS user that runs the MCP client**.

Web search uses the local CLI credentials and your account quota. The server does not perform interactive login or accept credentials as tool arguments. Your account must have access to `gpt-6-luna` and live web search. The implementation fixes the model to **`gpt-6-luna`** and reasoning effort to **`low`**.

The filesystem and terminal servers require neither Codex CLI nor an OpenAI account.

## Quick start

### 1. Install

```sh
git clone https://github.com/hikaMaeng/mcp.git
cd mcp
uv sync --locked
```

Keep this checkout and its `.venv`: the client launches the installed code from here.

### 2. Authenticate Codex CLI (web search only)

Install Codex CLI using the [official instructions](https://developers.openai.com/codex/cli). For an npm installation, Node.js is required:

```sh
npm install -g @openai/codex
codex --version
codex login
codex login status
```

If already logged in, check `codex login status` and continue. Confirm the **CLI** authentication state; the MCP process must be able to use that user's credentials and executable.

### 3. Configure your MCP client

Merge these entries into your existing `mcp.json` **`mcpServers` object**. Preserve other servers and do not add a duplicate `mcpServers` key. Omit either entry if you only need one server.

Replace `C:/path/to/mcp` with the **absolute checkout path**. This Windows example launches Python directly, so the GUI does not need to find `uv`:

```json
{
  "mcpServers": {
    "websearch": {
      "command": "C:/path/to/mcp/.venv/Scripts/python.exe",
      "args": ["-m", "websearch"]
    },
    "fileiomcp": {
      "command": "C:/path/to/mcp/.venv/Scripts/python.exe",
      "args": ["-m", "fileiomcp"]
    },
    "terminalmcp": {
      "command": "C:/path/to/mcp/.venv/Scripts/python.exe",
      "args": ["-m", "terminalmcp"]
    }
  }
}
```

On macOS/Linux, use `/absolute/path/to/mcp/.venv/bin/python` for each command. The `args` stay the same. In Windows JSON, use forward slashes or escape backslashes as `\\`.

Alternatively, launch through `uv`:

```json
{
  "mcpServers": {
    "websearch": {
      "command": "uv",
      "args": ["run", "--frozen", "--directory", "/absolute/path/to/mcp", "websearch"]
    },
    "fileiomcp": {
      "command": "uv",
      "args": ["run", "--frozen", "--directory", "/absolute/path/to/mcp", "fileiomcp"]
    },
    "terminalmcp": {
      "command": "uv",
      "args": ["run", "--frozen", "--directory", "/absolute/path/to/mcp", "terminalmcp"]
    }
  }
}
```

Replace the checkout path. If the GUI cannot find `uv`, use its absolute executable path or the direct Python configuration. Clients with a different configuration format need their own wrapper around the same `command`, `args`, and `env` fields.

### LM Studio

Open its MCP configuration editor and merge the entries above. On this Windows installation, the file is `%USERPROFILE%/.lmstudio/mcp.json`. Save and reconnect/enable the integrations to load the server definitions.

If Codex works in a terminal but is not found by the GUI, add this `env` object to the **websearch** entry, using your actual CLI path:

```json
"env": {
  "CODEX_MCP_CODEX_BIN": "C:/absolute/path/to/codex.exe"
}
```

A standard Windows npm `codex.cmd` is also supported when its adjacent official `node_modules/@openai/codex/bin/codex.js` and Node.js are available. Arbitrary `.cmd` wrappers are not supported.

All three servers reserve stdout for MCP messages. Running `uv run --frozen websearch`, `uv run --frozen fileiomcp`, or `uv run --frozen terminalmcp` manually waits for a client over stdin; these are not interactive command prompts or HTTP services.

## Tools

### Web search

Call `websearch` with:

```json
{"query": "Python asyncio official documentation", "max_results": 3}
```

`query` requires 1–2,000 nonblank characters; `max_results` is an integer from 1 to 10 (default: 5). Results include `title`, `url`, `snippet`, `published_at`, and `rank` in a versioned success/error envelope. Snippets are model summaries grounded in search results; unknown dates are `null`. Model and reasoning settings cannot be passed as arguments.

### Filesystem

| Tools | Operation |
| --- | --- |
| `directory_create`, `directory_delete` | Create a directory or delete an empty directory/tree |
| `directory_move`, `directory_copy` | Move or copy a directory tree |
| `file_create`, `file_append`, `file_delete` | Create/replace text, append chunks, or delete a file |
| `file_read` | Read numbered lines and the file's SHA-256 |
| `file_move`, `file_copy` | Move or copy a file |
| `file_edit_lines` | Delete/replace a line range or insert after a line |

Line ranges are **1-based and inclusive**. Replace lines 2–3:

```json
{"path": "C:/work/example.txt", "operation": "replace", "start_line": 2, "end_line": 3, "lines": ["new line 2", "new line 3"]}
```

Use `operation: "delete"` without `lines` to delete a range. Use `operation: "insert_after"` with `start_line` and `lines` to insert; line `0` inserts at the beginning. Each `lines` item must contain no newline characters.

Existing destinations require `overwrite: true`; an identical `file_create` retry is accepted. Inspect existing files before replacing them. For documents/code, create an empty file by omitting `content`, then send consecutive `file_append` chunks (prefer at most 800 characters each). Generate one call per response and wait for its result. This is guidance, not a schema length limit. If a connection fails, read the actual file before retrying an append: the previous chunk may already have been written.

**Filesystem access follows OS permissions; there is no configured allowed-directory sandbox.** Use absolute paths. Recursive deletion permanently removes the selected tree. Writes through symbolic links are rejected; exclusive creation requires hard-link support, such as NTFS. See [File I/O MCP](docs/file-io-mcp.md) for write and failure semantics.

### Terminal

`terminalmcp` exposes `terminal_run`. Example: `{"command":"Get-Process | Select-Object -First 5","timeout_seconds":30,"max_output_bytes":200000}`. Each call starts fresh Windows PowerShell on Windows or `/bin/sh` on macOS/Linux. On Windows, use PowerShell commands such as `Get-Process`; Linux commands such as `cat /proc/meminfo` are unavailable. Windows PowerShell output is configured as UTF-8, with OEM/ANSI code-page fallback when decoding captured output. Working-directory changes and shell state do not persist between calls. Optional `cwd` selects an existing working directory. While running, it sends periodic MCP progress notifications with recent output when the client supplies a progress token; clients may choose not to display them. MCP cancellation stops the process tree. Timeout is 1–600 seconds; stdout and stderr are each capped at 1,000,000 bytes (defaults: 30 seconds and 200,000 bytes per stream). Commands run with the MCP server user's OS permissions.

## Web search configuration

Set these in the websearch entry's `env` object. The original `CODEX_MCP_` prefix is retained for compatibility.

| Variable | Default | Purpose |
| --- | --- | --- |
| `CODEX_MCP_CODEX_BIN` | `codex` | CLI executable name or absolute path |
| `CODEX_MCP_TIMEOUT_SECONDS` | `180` | Deadline including queue wait; 1–600 seconds |
| `CODEX_MCP_MAX_CONCURRENCY` | `2` | Concurrent CLI processes per server; 1–8 |

Set the client's tool timeout longer than the server deadline (for example, 210 seconds for the default). Each search launches Codex in a temporary working directory with read-only sandboxing and live web search; shell, apps, and agent tools are disabled. User configuration and repository rules are ignored for search execution.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Server will not start | Run `uv sync --locked`; check the absolute executable path |
| `CODEX_NOT_FOUND` | Install the CLI or set `CODEX_MCP_CODEX_BIN`; GUI PATH can differ |
| `CODEX_FAILED` | Check CLI login, model access, network connectivity, and account limits |
| `TIMEOUT` | Check server/client deadlines and concurrent requests |
| Unterminated JSON / model failed to generate a tool call | Increase the client's output token limit or write smaller chunks; a complete call has not reached the server |
| `WebSocket closed by the client` | Inspect client logs and integration connection state; this message alone does not identify a filesystem failure |
| File already exists | Read it first; set `overwrite: true` only when replacement is intended |

## Documentation

Some detailed documents are currently in Korean. Installation and configuration are available in both README languages.

| Topic | Document |
| --- | --- |
| Purpose | [Overview](docs/overview.md) |
| Tool contracts | [API reference](docs/api.md) |
| Setup | [Usage](docs/usage.md) · [MCP JSON example](examples/mcp.json) |
| Filesystem behavior | [File I/O MCP](docs/file-io-mcp.md) |
| Limits | [Constraints](docs/constraints.md) |
| Design | [Architecture](docs/architecture.md) · [CLI internals](docs/internals.md) |
| Development checks | [Testing](docs/testing.md) |
