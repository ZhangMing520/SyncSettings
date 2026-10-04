# AGENTS.md — SyncSettingsReborn

Guidance for AI agents working in this repository.

## What this is

SyncSettingsReborn is a **Sublime Text plugin** (Python) that syncs your
`Packages/User` settings across machines via **GitHub Gists**. It is a
community-maintained revival of the unmaintained `SyncSettings` package and is
published on Package Control under the name `SyncSettingsReborn`.

Besides the Gist backend it also offers PackageSync-style sync:
- Offline **Zip backup / restore** of `Packages/User`
- **Backup Package List** only
- **Sync Online** (Dropbox / Google Drive / OneDrive folder) push/pull

Two entry points matter:
- `1_reloader.py` — package root module Sublime loads; reloads all submodules in
  dependency order on upgrade (see `mods_load_order`).
- `SyncSettingsReborn.py` — root module that imports commands + `auto_sync` and
  defines `plugin_loaded()` / `plugin_unloaded()`.

## Runtime environment (critical)

- Runs on **Sublime's embedded Python** (3.14 on current builds; `imp` was
  removed in 3.12). Use `importlib.reload`, never `imp.reload`.
- `sublime` and `sublime_plugin` are **builtins only inside Sublime** — they do
  NOT exist when running tests. The test suite shims them (see below).
- Package Control installs the runtime deps declared in `dependencies.json`
  (`requests`, `urllib3`, `idna`, `certifi`, `charset_normalizer`).

## How to run tests

A local `.venv` (Python 3.14) is available and works in the sandbox:

```bash
.venv/bin/python -m pytest tests/ -q
```

- `tests/conftest.py` + `tests/mocks/sublime_mock.py` provide `sublime` /
  `sublime_plugin` shims so the plugin modules import outside Sublime.
- `tests/mocks/` holds other fakes (e.g. gist API responses).
- Lint with flake8 (config in `.flake8`, max-line-length 127). CI also runs
  flake8 but targets old Pythons — ignore the CI matrix (3.5–3.9); develop
  against 3.14.
- **Do not add skipped tests or `# noqa` to silence real issues.** If a test
  can't run in the harness, fix the harness/mock instead.

## Module map (`sync_settings_reborn/`)

| Module | Responsibility |
|--------|----------------|
| `libs/path.py` | Key encoding. `canonical(name) = encode(decode(name))` — the plugin's internal key space (percent-encoded). Foreign/literal-separator names like `sub/C.sublime-settings` collapse to the same canonical key. |
| `libs/gist.py` | GitHub Gist API client (`Gist.from_settings().proxies` for proxy). |
| `libs/settings.py` | Settings access + `migrate_legacy()` (imports old `SyncSettings` config on first run). |
| `libs/file.py` / `logger.py` | File helpers; logging. |
| `sync_manager.py` | Core sync engine: `fetch_files` (download via **raw_url + proxy**), `download_file`, `install_missing_packages`, `get_content` (strict UTF-8 — binary files are skipped, NOT uploaded). |
| `auto_sync.py` | Background daemon (`AutoSync`): delta push/pull, three-way merge, conflict backup to `~/.sync_settings_reborn/conflicts/<ts>/`, persisted baseline in `~/.sync_settings_reborn/sync.json`. |
| `sync_version.py` | Reads/writes `sync.json` (atomic temp-file + `os.replace`). |
| `thread_progress.py` | Background worker that runs commands without blocking the UI. |
| `commands/` | One file per command: `upload`, `download`, `delete`, `backup`, `restore`, `sync_online`, `open_logs`, plus `decorators.py`. |

## Domain concepts (read before touching sync logic)

- **Gist API content vs raw_url.** The inline `content` field from
  `api.github.com/gists` is **truncated (>~1MB) and omitted for git-pushed
  files**. The `raw_url` (raw.githubusercontent.com) is always the full file.
  → Manual Download and auto-sync both fetch through **raw_url**, never inline
  `content`. Do not reintroduce inline-content reads for file bodies.
- **`name_map`: canonical key → list of real remote filenames.** A gist file
  created by an external tool may use a literal path separator (`sub/C...`) —
  a "foreign" name. `_name_map(g)` groups these. `_build_payload` decides
  rename forms (`{foreign: {filename: canonical, content}}`) vs update/null.
  A brand-new gist has no remote names, so `_initial_push` passes `{}`.
- **Three-way merge / delta.** `MergeInputs` dataclass consolidates the
  present/deleted/conflicts/remote/local state. `_apply_and_push` applies
  remote-wins and pushes local deltas. `_remote_hashes` hashes only files whose
  content was actually fetched.
- **Proxy.** `http_proxy` / `https_proxy` settings flow via
  `Gist.from_settings().proxies` into both the API client and `fetch_files`.
  Manual Download must honour them (it previously did not — do not regress).
- **Thread safety.** `AutoSync._lock` serializes the daemon cycle
  (`_sync_once`) against `adopt()` (called by manual Upload/Download and at
  startup). `_sync_once` never calls `adopt`, so the non-reentrant `Lock` is
  safe — keep it that way. Long-held lock across network I/O is intentional.
- **Binary files.** `get_content` decodes as UTF-8 and returns `''` on
  `UnicodeDecodeError` (file is then not uploaded). Never broad-except this away.

## Package Control submission

- `SUBMISSION.md` documents the submission flow (no zip upload; register the
  Git repo in `wbond/package_control_channel`, releases come from **git tags**).
- `messages.json` + `messages/*.txt` are the install/release notes Package
  Control shows. Add an entry per release.
- Releases are read from **tags** (e.g. `v4.1.0`) — there must be a tag for a
  version to be distributed. `repository.json` lives in the channel repo, NOT
  here.

## Commit / workflow conventions

- Keep commits focused; prefer one logical change per commit with a clear
  imperative subject (e.g. `fix: ...`, `feat: ...`, `refactor: ...`).
- Update `CHANGELOG.md` for user-visible changes.
- After editing sync logic, run the full suite (`pytest tests/ -q`) and confirm
  green before committing.
- `SyncSettingsReborn.sublime-settings` is the user-facing settings schema —
  document new settings there with comments.
