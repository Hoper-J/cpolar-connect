# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Audience**: LLM-driven engineering agents and human developers working on the CpolarAutoUpdater project

## Project Overview

CpolarAutoUpdater is a Python CLI tool (Python ≥3.8) that automates cpolar tunnel management and SSH connections. It solves the problem of dynamic host/port changes in cpolar's free version by automatically updating configurations and establishing SSH connections to remote servers through cpolar tunnels.

## Required Development Workflow

Before committing changes, run these commands in sequence:

```bash
# Install dependencies
pip install -e .

# Format and lint
black src/ --line-length=88
isort src/ --profile=black

# Type checking
mypy src/cpolar_connect --python-version=3.8

# Run tests (when implemented)
pytest tests/ --cov=cpolar_connect
```

## Repository Structure

| Path | Purpose |
|------|---------|
| `src/cpolar_connect/` | Main library source code |
| `├─ cli.py` | CLI entry point, command parsing |
| `├─ config.py` | Configuration management with Pydantic |
| `├─ auth.py` | Cpolar authentication logic |
| `├─ tunnel.py` | Tunnel discovery and management |
| `├─ ssh.py` | SSH operations and config updates |
| `├─ i18n.py` | Internationalization (Chinese/English) |
| `└─ exceptions.py` | Custom exception classes |
| `tests/` | Test suite (not yet implemented) |
| `docs/` | Documentation directory |
| `config.txt.example` | Legacy configuration example |
| `auto_tunnel.py` | Legacy script (being deprecated) |

## Development Commands

### Environment Setup
```bash
git clone https://github.com/Hoper-J/CpolarAutoUpdater
cd CpolarAutoUpdater
pip install -e .  # Install in development mode
```

### Running the Application
```bash
# New CLI tool (recommended)
cpolar-connect              # Default: connect to server
cpolar-connect init         # Initialize configuration
cpolar-connect config show  # Display configuration

# Legacy script (deprecated)
python auto_tunnel.py
```

### Code Quality Tools
```bash
# Format code with Black
black src/ --line-length=88

# Sort imports with isort
isort src/ --profile=black

# Type checking with mypy
mypy src/cpolar_connect --python-version=3.8

# Run tests (when available)
pytest tests/ --cov=cpolar_connect
```

## Architecture Overview

### Module Structure
The project follows a modular architecture under `src/cpolar_connect/`:

- **cli.py**: Entry point for the CLI application. Handles command parsing and orchestrates the connection workflow
- **config.py**: Configuration management using Pydantic models. Handles JSON config files and secure password storage via keyring
- **auth.py**: Cpolar authentication logic. Manages login sessions and credentials
- **tunnel.py**: Tunnel information retrieval and management. Parses cpolar dashboard to get current tunnel details
- **ssh.py**: SSH key generation, config updates, and connection management. Handles ~/.ssh/config modifications
- **i18n.py**: Internationalization support for Chinese/English messages
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
- Legacy config: `config.txt` (INI format, being migrated)

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

### Testing Guidelines (Future)
- Tests should be atomic and self-contained
- Use parameterization for testing multiple scenarios
- Mock external services (cpolar API, SSH connections)
- Test both success and failure paths
- Coverage target: >80% for core modules

## Migration Path

The project is transitioning from script-based (`auto_tunnel.py`) to package-based (`cpolar-connect`) architecture:

1. **Legacy Support**: `auto_tunnel.py` remains functional but deprecated
2. **Configuration Migration**: Use `migrate_to_cli.py` to convert `config.txt` to new JSON format
3. **Password Migration**: Move from plain text to keyring/environment variable storage
4. **Path Changes**: Config moves from project directory to `~/.cpolar_connect/`

## Important Notes

- Tests directory exists but tests are not yet implemented - contributions welcome
- Supports both Chinese and English through i18n module
- Requires cpolar server setup as documented in README
- Handles automatic SSH key generation and upload on first connection
- Port forwarding configuration supports multiple ports (comma-separated)