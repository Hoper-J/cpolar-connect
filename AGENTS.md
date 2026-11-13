# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Audience**: LLM-driven engineering agents and human developers working on the cpolar-connect project

## Project Overview

cpolar-connect is a Python CLI tool (Python ≥3.8) that automates cpolar tunnel management and SSH connections. It solves the problem of dynamic host/port changes in cpolar's free version by automatically updating configurations and establishing SSH connections to remote servers through cpolar tunnels.

## Required Development Workflow

Before committing changes, run these commands in sequence:

```bash
# Sync dependencies (including dev)
uv sync --extra dev

# Format and lint
uv run black src/ tests/ --line-length=88
uv run isort src/ tests/ --profile=black

# Run tests
uv run pytest tests/ -v
```

## Repository Structure

| Path | Purpose |
|------|---------|
| `src/cpolar_connect/` | Main library source code |
| `├─ cli.py` | CLI entry point, command parsing, output rendering |
| `├─ config.py` | Configuration management with Pydantic |
| `├─ auth.py` | Cpolar authentication logic |
| `├─ tunnel.py` | Tunnel discovery and management |
| `├─ ssh.py` | SSH operations and config updates |
| `├─ doctor.py` | Diagnostic tool for troubleshooting |
| `├─ i18n.py` | Internationalization (Chinese/English) |
| `├─ prompts.py` | Clack-style step prompts for CLI |
| `└─ exceptions.py` | Custom exception classes |
| `tests/` | Test suite |
| `├─ conftest.py` | Shared fixtures: real HTML samples, autouse isolation of home/env/language, a private key writer, a loopback SSH server |
| `├─ test_auth.py` | Authentication tests |
| `├─ test_tunnel.py` | Tunnel parsing & selection tests |
| `├─ test_config_basic.py` | Configuration tests |
| `├─ test_accounts.py` | Account name validation & per-account paths |
| `├─ test_migration.py` | Legacy layout migration tests |
| `├─ test_cli_accounts.py` | Multi-account CLI surface tests |
| `├─ test_hostkey.py` | Host key TOFU, alias/user safety & ssh_config rendering tests |
| `├─ test_ssh_upload.py` | Key pre-check, upload & passwordless bootstrap tests |
| `├─ test_connect_flow.py` | Connect flow tests: bootstrap, hints after errors, what a failed run leaves in ~/.ssh/config |
| `├─ test_doctor.py` | Doctor checks tests |
| `├─ test_prompts.py` | Prompt cancellation semantics |
| `├─ test_i18n_keys.py` | i18n guards: keys, placeholders, commands that name the account |
| `├─ test_verify_credentials.py` | Init-time credential verification |
| `├─ test_status_local_only.py` | Status command tests |
| `└─ e2e/test_real_sshd.py` | Connect flow against a real sshd (opt-in via `CPOLAR_E2E_*`, run by CI) |
| `.github/workflows/ci.yml` | CI: format check, tests on Linux/macOS/Windows (Python 3.8 & 3.13), end-to-end tests against Linux and Windows sshd |
| `docs/` | Documentation directory |

## Development Commands

### Environment Setup
```bash
git clone https://github.com/Hoper-J/cpolar-connect
cd cpolar-connect
uv sync --extra dev  # Install with dev dependencies
```

### Running the Application
```bash
cpolar-connect              # Default: connect to server (short alias: cpc)
cpolar-connect init         # Initialize configuration (init -a <name> creates an account)
cpolar-connect use <name>   # Switch current account
cpolar-connect list         # List accounts (alias of `account list`)
cpolar-connect config show  # Display configuration
cpolar-connect status       # Show tunnel status
cpolar-connect doctor       # Diagnose issues
cpolar-connect -a <name> …  # Run any command against a specific account
```

### Code Quality Tools
```bash
# Format code with Black
uv run black src/ tests/ --line-length=88

# Sort imports with isort
uv run isort src/ tests/ --profile=black

# Run tests
uv run pytest tests/ -v
```

## Architecture Overview

### Module Structure
The project follows a modular architecture under `src/cpolar_connect/`:

- **cli.py**: Entry point for the CLI application. Handles command parsing, orchestrates the connection workflow, and renders all user-facing output (i18n-aware)
- **config.py**: Configuration management using Pydantic models. Owns account resolution/validation, per-account paths, legacy-layout migration, and password file storage. Returns data for CLI to render
- **auth.py**: Cpolar authentication logic. Manages login sessions and credentials
- **tunnel.py**: Tunnel information retrieval and management. Parses cpolar dashboard to get current tunnel details
- **ssh.py**: SSH key generation, config updates, and connection management. Handles ~/.ssh/config modifications and host key verification (`AliasHostKeyPolicy`: TOFU keyed by SSH alias). Returns status for CLI to render
- **doctor.py**: Diagnostic tool that checks configuration, network, authentication, SSH setup, tunnel status, and whether the tunnel's host name resolves on this network (it does not on some campus networks, and then everything else is in order while connecting fails)
- **i18n.py**: Internationalization support for Chinese/English messages. Priority: CPOLAR_LANG env var > current account's config (with default-account and legacy-path fallbacks) > system locale > Chinese
- **prompts.py**: Clack-style step prompts providing clean, step-by-step CLI interaction (intro/outro, steps, spinners, confirmations). A spinner left open by an exception is closed by the next output call, so errors start on their own line
- **exceptions.py**: Custom exception classes for different error scenarios

### Connection Workflow
1. **Account Resolution**: `-a` flag > `CPOLAR_ACCOUNT` env > current file > `default`
2. **Authentication**: Login to cpolar using the resolved account's credentials
3. **Tunnel Discovery**: Fetch current tunnel information (host/port) from cpolar dashboard. The account's `tunnel_name` picks a tunnel by dashboard name (several machines can share one cpolar account); unset, the first tunnel to local port 22 is used and any other SSH tunnels are reported as a warning. Either way a tunnel to local port 22 comes before other TCP tunnels; when there is none, the first TCP tunnel is used and the warning says so. Same-named tunnels cannot be told apart and are warned about too. A `tunnel_name` that is not online while other tunnels are raises `TunnelNameNotFoundError` (wrong name, or that machine is down)
4. **SSH Test**: Key auth with what the generated Host block offers: the configured key (`ssh_key_path`) plus ssh-agent keys (`IdentityFile` without `IdentitiesOnly`), but not the default key files, which an explicit `IdentityFile` makes `ssh` skip. Agent keys are left out when the user's own ssh configuration keeps `ssh` from using them (`IdentitiesOnly yes`, `IdentityAgent none`; asked of `ssh -G` by `_ssh_offers_agent_keys`). The key file must be one `ssh` will use: on POSIX a key of the user's own that group or others can read is refused with the `chmod` to run (`_require_key_file_ssh_accepts`). Server host key is TOFU-recorded and verified per alias (`AliasHostKeyPolicy`): once a key is on record, only a key on record is accepted, a key of another type included (it would let anyone on the tunnel's path in), and the server is asked for the recorded key type first, as `ssh` does, so that a server with a key per type still passes. A damaged record in the host key file is an error, never skipped. Only missing/rejected keys lead to bootstrap; an unreachable server, a failed handshake, an unloadable key or an unusable host key file raises `SSHError`. `SSHManager._open_client` tells these apart by phase: after the host key is accepted, a failure is about credentials, unless the connection itself broke (`OSError`), which is reported as that. Before that point no SSH session came about and nothing was learned about the server: that is the subclass `ServerUnreachableError` (the name does not resolve, nothing answers, the handshake fails). A name that does not resolve gets a message of its own, because the cause is the client network's DNS (some networks do not resolve tunnel host names) and advice about sshd would mislead
5. **Bootstrap (first connection only)**: Generate key pair, install public key via existing SSH keys (agent/default), falling back to server password (an empty password is still tried, never skipped; a server that offers no password login at all raises `PasswordLoginUnavailableError`). What is installed is the line of the `.pub` file, which must be the public half of the configured private key (`_public_key_to_install`). The key always lands on a line of its own (a missing final newline in `authorized_keys` is added first), and "already installed" means an entry as sshd reads it (`_authorized_key`: the key at the start of the line or after one options field), never a substring match. The commands are kept to what sh, bash, zsh, dash, csh and tcsh all understand (no `2>/dev/null`, no `echo`); the real-shell tests run them in each. Every remote command goes through `SSHManager._exec`, which gives up after `_REMOTE_COMMAND_TIMEOUT` seconds of silence (a tunnel can die without a word). A server that introduces itself as OpenSSH for Windows gets none of the POSIX commands (cmd and PowerShell reject them) but one PowerShell script, sent as `powershell.exe -EncodedCommand` so that no default shell interprets it (`_WINDOWS_INSTALL_SCRIPT` in `ssh.py`): it picks the file sshd reads for the account (`administrators_authorized_keys` for administrators unless `sshd_config` has that switched off, else the profile's `.ssh\authorized_keys`) and gives the same guarantees. If that fails, `WindowsServerKeyError` makes the CLI say how to install the key by hand
6. **Config Update**: Rewrite the alias's ~/.ssh/config Host block (`StrictHostKeyChecking accept-new` + per-account `UserKnownHostsFile`). This happens once key authentication works, and in one more case: when the SSH test of step 4 ends in `ServerUnreachableError`, the block is written before the run gives up, and a hint says so (`_record_unreached_address` in `cli.py`). The address is the dashboard's and stays right when this machine cannot get there, and ssh, editors and users' own scripts look it up in the Host block (issue #3: a campus DNS that will not resolve the tunnel's name, which the user resolves by other means). Not even then if the tunnel was one of several that qualified equally (`TunnelInfo.other_candidates`): with several machines on one cpolar login it may be another machine's, and the address in the block may still be the right one. No other failure writes the block: a server whose host key was refused must never become what the alias points at, and a first connection that was given up leaves nothing behind. A config file that cannot be read or written is an `SSHError` naming the file (`_reports_config_file_errors`), never a traceback
7. **Connection**: Establish SSH connection with port forwarding if configured

### Configuration Storage (multi-account)
- Accounts root: `~/.cpolar_connect/accounts/<name>/` (one dir per account, mode 700)
- Main config: `~/.cpolar_connect/accounts/<name>/config.json`
- Passwords: `~/.cpolar_connect/accounts/<name>/.password` or environment variable `CPOLAR_PASSWORD` (applies to ALL accounts)
- Host keys: `~/.cpolar_connect/accounts/<name>/known_hosts` (TOFU, keyed by SSH alias)
- Current account: `~/.cpolar_connect/current`; resolution priority `-a` flag > `CPOLAR_ACCOUNT` env > current file > `default`
- Legacy single-account layout migrates automatically into `accounts/default/` on first run
- SSH keys: Default `~/.ssh/id_rsa_cpolar`, generated as RSA (configurable; may point at an existing passphrase-free RSA/Ed25519/ECDSA key, which skips the upload when the server already accepts it; RSA and ECDSA keys may also be in PKCS#8 form, Ed25519 keys may not, because most builds of `ssh` cannot read that)
- Logs: `~/.cpolar_connect/logs/cpolar.log` (shared across accounts)

### Key Dependencies
- **paramiko** (≥ 3.2, for `transport_factory`): SSH operations and key management
- **cryptography**: reads PKCS#8 private keys, which paramiko cannot
- **requests/beautifulsoup4**: Web scraping cpolar dashboard
- **click/rich**: CLI interface and terminal formatting
- **pydantic**: Configuration validation and type safety

## Development Standards

### Code Standards
- Python ≥3.8 with type annotations where applicable
- Follow existing patterns and maintain consistency
- Prioritize readable, understandable code over clever optimizations
- Use Pydantic for configuration validation
- Handle errors with specific exception types from `exceptions.py`

### Error Handling Patterns
- Never use bare `except` - be specific with exception types
- Use custom exceptions: `ConfigError`, `AuthenticationError`, `TunnelError`, `TunnelNotFoundError`, `TunnelNameNotFoundError`, `SSHError`, `ServerUnreachableError`, `HostKeyChangedError`, `KeyInstallError` (`WindowsServerKeyError`, `PasswordLoginUnavailableError`), `NetworkError`
- `HostKeyChangedError` must never be swallowed or downgraded (it signals a possible MITM); `TunnelNotFoundError` triggers the server-command hint; its subclass `TunnelNameNotFoundError` adds the hint to fix `tunnel.name`; `ServerUnreachableError` is the one failure after which the connect flow still writes the Host block (see step 6), so raise it only where the server was never reached
- Hints that contain a command must name the account (`cpolar-connect -a <name> …`) so they work as printed for a non-current account. A hint that follows an error is printed with `Prompts.log_hint`, which quiet mode (`-q`) does not suppress; `log_info` is for progress. Which hint follows which error is decided in one place, `_print_remedy` in `cli.py`. `test_i18n_keys.py` enforces the rule on the message texts, and checks that every `_()` call supplies the placeholders of its message
- Free-form values (tunnel names, paths, error text) are data: `rich.markup.escape()` them before Rich rendering, and render ssh_config values through `_config_token`/`_config_path`
- Provide clear error messages with context for debugging
- Log errors appropriately using the configured logging level

### Security Considerations
- Password file (`~/.cpolar_connect/accounts/<name>/.password`) uses 600 permissions (owner read/write only)
- Account names are validated (whitelist regex + reserved names) at every entry point (`-a`, `CPOLAR_ACCOUNT`, `current` file); they feed both filesystem paths and SSH aliases
- SSH keys should have appropriate permissions (600). On a Windows client the equivalent is an access list of the user, SYSTEM and administrators with nothing inherited (`_restrict_to_user` in `ssh.py`), applied to the generated key, and on every run to the key and `~/.ssh/config` (`_keep_acceptable_to_windows_ssh`), which also repairs files left by versions up to 0.3.0. Never create `~/.ssh` with mode `0o700` there (`_make_ssh_dir`): Python ≥ 3.12.4 turns that mode into an inheritable "OWNER RIGHTS" entry, and `ssh.exe` then rejects every key and config file in the directory
- Validate all user inputs, especially for SSH operations
- Sanitize configuration values before using in shell commands. Text written on the server goes through `printf '%s\n' '<single-quoted text>'`, never `echo`: the `echo` of zsh, dash and sh expands backslash sequences, and a public key's comment is free text. `~/.ssh/config` is the user's file and need not be UTF-8: it is read and written with `errors="surrogateescape"` so that other bytes pass through unchanged

### Testing Guidelines
- Tests use real HTML samples from cpolar dashboard (stored in `conftest.py`)
- Use `pytest` with fixtures for isolation
- Every test is isolated by the autouse fixture in `conftest.py`: home (`Path.home` and `HOME`) points at `tmp_path`, `CPOLAR_ACCOUNT`/`CPOLAR_PASSWORD`/`SSH_AUTH_SOCK` are unset, the `ssh -G` question about agent keys is answered without asking (it would read the real `~/.ssh/config`), and the i18n singleton is reset and pinned to English — a developer's real env vars/homedir/locale must never leak into tests. Do not undo it; a test that needs another language or account sets it explicitly
- Do NOT monkeypatch `os.name` to simulate Windows (it breaks pathlib's platform dispatch); patch `platform.system` instead
- The suite also runs on Windows in CI. Mark a test that needs POSIX permission bits or a POSIX shell with `@pytest.mark.posix_only` (skipped on Windows); everything else must pass there
- `tests/e2e/` drives the connect flow against a real sshd, with only cpolar login and tunnel discovery replaced. It is skipped unless `CPOLAR_E2E_SSH_KEY` is set (variables are listed in the module docstring) and it writes to the target account's `authorized_keys`: CI points it at throwaway Linux and Windows machines, never point it at a server that matters
- Mock external services (cpolar API, SSH connections). Where the SSH handshake itself is the subject (which host key a server presents), the `ssh_server` fixture in `conftest.py` starts a real paramiko server on the loopback interface instead
- Test both success and failure paths
- Run tests: `uv run pytest tests/ -v`

## Important Notes

- Supports both Chinese and English through i18n module
- Requires cpolar server setup as documented in README
- Handles automatic SSH key generation and upload on first connection (tries existing SSH keys via agent/default keys before asking for the server password)
- Port forwarding configuration supports multiple ports (comma-separated)