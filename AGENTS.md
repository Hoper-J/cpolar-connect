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
| `├─ conftest.py` | Shared fixtures with real HTML samples |
| `├─ test_auth.py` | Authentication tests |
| `├─ test_tunnel.py` | Tunnel parsing tests |
| `├─ test_config_basic.py` | Configuration tests |
| `├─ test_accounts.py` | Account name validation & per-account paths |
| `├─ test_migration.py` | Legacy layout migration tests |
| `├─ test_cli_accounts.py` | Multi-account CLI surface tests |
| `├─ test_hostkey.py` | Host key TOFU & alias safety tests |
| `├─ test_ssh_upload.py` | Key upload & passwordless bootstrap tests |
| `├─ test_connect_flow.py` | Connect flow bootstrap tests |
| `├─ test_doctor.py` | Doctor checks tests |
| `├─ test_prompts.py` | Prompt cancellation semantics |
| `├─ test_i18n_keys.py` | i18n key completeness guard |
| `├─ test_verify_credentials.py` | Init-time credential verification |
| `└─ test_status_local_only.py` | Status command tests |
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
- **doctor.py**: Diagnostic tool that checks configuration, network, authentication, SSH setup, and tunnel status
- **i18n.py**: Internationalization support for Chinese/English messages. Priority: CPOLAR_LANG env var > current account's config (with default-account and legacy-path fallbacks) > system locale > Chinese
- **prompts.py**: Clack-style step prompts providing clean, step-by-step CLI interaction (intro/outro, steps, spinners, confirmations)
- **exceptions.py**: Custom exception classes for different error scenarios

### Connection Workflow
1. **Account Resolution**: `-a` flag > `CPOLAR_ACCOUNT` env > current file > `default`
2. **Authentication**: Login to cpolar using the resolved account's credentials
3. **Tunnel Discovery**: Fetch current tunnel information (host/port) from cpolar dashboard
4. **SSH Test**: Key auth with the dedicated key; server host key is TOFU-recorded and verified per alias (`AliasHostKeyPolicy`)
5. **Bootstrap (first connection only)**: Generate key pair, install public key via existing SSH keys (agent/default), falling back to server password
6. **Config Update**: Rewrite the alias's ~/.ssh/config Host block (`StrictHostKeyChecking accept-new` + per-account `UserKnownHostsFile`)
7. **Connection**: Establish SSH connection with port forwarding if configured

### Configuration Storage (multi-account)
- Accounts root: `~/.cpolar_connect/accounts/<name>/` (one dir per account, mode 700)
- Main config: `~/.cpolar_connect/accounts/<name>/config.json`
- Passwords: `~/.cpolar_connect/accounts/<name>/.password` or environment variable `CPOLAR_PASSWORD` (applies to ALL accounts)
- Host keys: `~/.cpolar_connect/accounts/<name>/known_hosts` (TOFU, keyed by SSH alias)
- Current account: `~/.cpolar_connect/current`; resolution priority `-a` flag > `CPOLAR_ACCOUNT` env > current file > `default`
- Legacy single-account layout migrates automatically into `accounts/default/` on first run
- SSH keys: Default `~/.ssh/id_rsa_cpolar` (configurable)
- Logs: `~/.cpolar_connect/logs/cpolar.log` (shared across accounts)

### Key Dependencies
- **paramiko**: SSH operations and key management
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
- Use custom exceptions: `ConfigError`, `AuthenticationError`, `TunnelError`, `TunnelNotFoundError`, `SSHError`, `HostKeyChangedError`, `NetworkError`
- `HostKeyChangedError` must never be swallowed or downgraded (it signals a possible MITM); `TunnelNotFoundError` triggers the server-command hint
- Provide clear error messages with context for debugging
- Log errors appropriately using the configured logging level

### Security Considerations
- Password file (`~/.cpolar_connect/accounts/<name>/.password`) uses 600 permissions (owner read/write only)
- Account names are validated (whitelist regex + reserved names) at every entry point (`-a`, `CPOLAR_ACCOUNT`, `current` file); they feed both filesystem paths and SSH aliases
- SSH keys should have appropriate permissions (600)
- Validate all user inputs, especially for SSH operations
- Sanitize configuration values before using in shell commands

### Testing Guidelines
- Tests use real HTML samples from cpolar dashboard (stored in `conftest.py`)
- Use `pytest` with fixtures for isolation
- Isolate the filesystem and environment in every test touching config/CLI: `monkeypatch.setattr(Path, "home", lambda: tmp_path)` plus `monkeypatch.delenv("CPOLAR_ACCOUNT"/"CPOLAR_PASSWORD", raising=False)` — a developer's real env vars/homedir must never leak into tests
- Do NOT monkeypatch `os.name` to simulate Windows (it breaks pathlib's platform dispatch); patch `platform.system` instead
- Mock external services (cpolar API, SSH connections)
- Test both success and failure paths
- Run tests: `uv run pytest tests/ -v`

## Important Notes

- Supports both Chinese and English through i18n module
- Requires cpolar server setup as documented in README
- Handles automatic SSH key generation and upload on first connection (tries existing SSH keys via agent/default keys before asking for the server password)
- Port forwarding configuration supports multiple ports (comma-separated)