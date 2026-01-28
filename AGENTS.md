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
uv run black src/ --line-length=88
uv run isort src/ --profile=black

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
cpolar-connect              # Default: connect to server
cpolar-connect init         # Initialize configuration
cpolar-connect config show  # Display configuration
cpolar-connect status       # Show tunnel status
cpolar-connect doctor       # Diagnose issues
```

### Code Quality Tools
```bash
# Format code with Black
uv run black src/ --line-length=88

# Sort imports with isort
uv run isort src/ --profile=black

# Run tests
uv run pytest tests/ -v
```

## Architecture Overview

### Module Structure
The project follows a modular architecture under `src/cpolar_connect/`:

- **cli.py**: Entry point for the CLI application. Handles command parsing, orchestrates the connection workflow, and renders all user-facing output (i18n-aware)
- **config.py**: Configuration management using Pydantic models. Handles JSON config files and secure password storage via keyring. Returns data for CLI to render
- **auth.py**: Cpolar authentication logic. Manages login sessions and credentials
- **tunnel.py**: Tunnel information retrieval and management. Parses cpolar dashboard to get current tunnel details
- **ssh.py**: SSH key generation, config updates, and connection management. Handles ~/.ssh/config modifications. Returns status for CLI to render
- **doctor.py**: Diagnostic tool that checks configuration, network, authentication, SSH setup, and tunnel status
- **i18n.py**: Internationalization support for Chinese/English messages. Priority: CPOLAR_LANG env var > config file > system locale
- **prompts.py**: Clack-style step prompts providing clean, step-by-step CLI interaction (intro/outro, steps, spinners, confirmations)
- **exceptions.py**: Custom exception classes for different error scenarios

### Connection Workflow
1. **Authentication**: Login to cpolar using stored/provided credentials
2. **Tunnel Discovery**: Fetch current tunnel information (host/port) from cpolar dashboard
3. **SSH Setup**: Generate SSH keys if needed, upload public key to server
4. **Config Update**: Update local ~/.ssh/config with new tunnel information
5. **Connection**: Establish SSH connection with port forwarding if configured

### Configuration Storage
- Main config: `~/.cpolar_connect/config.json`
- Passwords: System keyring (secure) or environment variable `CPOLAR_PASSWORD`
- SSH keys: Default `~/.ssh/id_rsa_cpolar` (configurable)
- Logs: `~/.cpolar_connect/logs/cpolar.log`

### Key Dependencies
- **paramiko**: SSH operations and key management
- **requests/beautifulsoup4**: Web scraping cpolar dashboard
- **click/rich**: CLI interface and terminal formatting
- **keyring**: Secure password storage
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
- Use custom exceptions: `AuthenticationError`, `TunnelError`, `SSHError`, `NetworkError`
- Provide clear error messages with context for debugging
- Log errors appropriately using the configured logging level

### Security Considerations
- **NEVER** store passwords in plain text - use keyring or environment variables
- SSH keys should have appropriate permissions (600)
- Validate all user inputs, especially for SSH operations
- Sanitize configuration values before using in shell commands

### Testing Guidelines
- Tests use real HTML samples from cpolar dashboard (stored in `conftest.py`)
- Use `pytest` with fixtures for isolation
- Mock external services (cpolar API, SSH connections)
- Test both success and failure paths
- Run tests: `uv run pytest tests/ -v`

## Important Notes

- Supports both Chinese and English through i18n module
- Requires cpolar server setup as documented in README
- Handles automatic SSH key generation and upload on first connection
- Port forwarding configuration supports multiple ports (comma-separated)