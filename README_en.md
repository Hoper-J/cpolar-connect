# Cpolar Connect

<div align="center">

[![PyPI version](https://img.shields.io/pypi/v/cpolar-connect.svg)](https://pypi.org/project/cpolar-connect/)
[![Python](https://img.shields.io/pypi/pyversions/cpolar-connect.svg)](https://pypi.org/project/cpolar-connect/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[中文](./README.md) | English

**🚀 A command-line tool for automating cpolar tunnel management and SSH connections**

</div>

## ✨ Why This Tool?

The free version of cpolar resets tunnel addresses periodically, requiring you to:
1. Log in to the cpolar website to check the new address
2. Manually update SSH configuration
3. Remember the new port number

**Cpolar Connect solves all these problems.**

## 🎯 Key Features

- 🔄 **Auto-update**: Automatically fetch the latest cpolar tunnel address
- ⚡ **One-click Connection**: No need to remember addresses and ports
- 🔑 **SSH Keys**: Automatic configuration for passwordless login
- 📦 **Simple Installation**: Ready to use with one command

## 📦 Installation

### Method 1: Using uv (Recommended, Fastest)

First install uv:

**Linux/macOS:**
```bash
# Using official installer
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip
pip install uv
```

**Windows:**
```powershell
# Using PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or using pip
pip install uv
```

Then run cpolar-connect:
```bash
# Run directly (no installation needed)
uvx cpolar-connect

# Or install to system
uv tool install cpolar-connect
```

### Method 2: Using pipx (Isolated Environment)

```bash
# Install
pipx install cpolar-connect

# Upgrade
pipx upgrade cpolar-connect
```

### Method 3: Using pip

```bash
pip install cpolar-connect
```

## 🚀 Quick Start

### Server Configuration

> Server needs cpolar installed and running. See [Server Setup Guide](docs/SERVER_SETUP_en.md)

Quick setup (Linux):
```bash
# 1. Install cpolar
curl -L https://www.cpolar.com/static/downloads/install-release-cpolar.sh | sudo bash

# 2. Configure authentication (register cpolar account first)
cpolar authtoken YOUR_TOKEN

# 3. Enable auto-start
sudo systemctl enable cpolar
sudo systemctl start cpolar

# 4. Check username (needed for client configuration)
whoami
```

### Client Configuration

#### 1️⃣ Initialize Configuration

```bash
cpolar-connect init
```

Interactive setup wizard (3 steps):

```
┌ Cpolar Connect Setup
◆  Step 1: Cpolar Account
│  Enter cpolar username: your@email.com
│  ✓ Username: your@email.com
│  Enter cpolar password: ********
│  ✓ Password saved
│  ◌ Verifying account...
│  ✓ Account verified
◆  Step 2: Server Configuration
│  Enter server username: root
│  ✓ Server user: root
│  Enter ports to forward (comma-separated) (8888,6666): 8888
│  ✓ Ports: 8888
◆  Step 3: Connection Options
│  Auto-connect after update? (Y/n):
│  ✓ Auto connect: Yes
│
│  ─── Configuration Summary ───
│  Username:    your@email.com
│  Password:    Yes
│  Server user: root
│  Ports:       8888
│  Auto connect: Yes
│
└ Setup complete! Run 'cpolar-connect' to connect.
```

#### 2️⃣ Connect to Server

```bash
# Direct connection
cpolar-connect

# Or provide password via environment variable
CPOLAR_PASSWORD=your_password cpolar-connect
```

**That's it!** The tool will automatically:
- Log in to cpolar to get the latest address
- Generate SSH keys (first time)
- Configure passwordless login
- Establish connection and forward ports

## ⚙️ Configuration Management

### View Configuration
```bash
cpolar-connect config show
```

### Modify Configuration
```bash
# Change server user
cpolar-connect config set server.user root

# Change ports
cpolar-connect config set server.ports 8080,3000

# Edit config file directly
cpolar-connect config edit
```

### Switch Language
```bash
# Chinese
cpolar-connect language zh

# English
cpolar-connect language en
```

### View Status
```bash
cpolar-connect status
```

Shows current tunnel address, SSH configuration, etc. (without connecting):

| Field | Value |
|-------|-------|
| Tunnel | tcp://x.tcp.vip.cpolar.cn:xxxxx |
| Host | x.tcp.vip.cpolar.cn |
| Port | xxxxx |
| SSH Alias | cpolar-server |
| SSH Key | ~/.ssh/id_rsa_cpolar |
| Auto Connect | Yes |
| Forward Ports | 8888 |

## 🔒 Password Management

### Option 1: Save During Init (Recommended)
Enter password when running `cpolar-connect init`, it will be stored in `~/.cpolar_connect/.password` file.

### Option 2: Environment Variable
```bash
export CPOLAR_PASSWORD=your_password
cpolar-connect
```

### Option 3: Provide via Environment Variable
Press Enter to skip password during init, then provide it via the `CPOLAR_PASSWORD` environment variable before connecting.

## 🛡️ Host Key Verification

Since v0.2.4, the tool verifies the server's SSH host key to prevent man-in-the-middle attacks:

- On first connection the server host key is recorded in `~/.cpolar_connect/known_hosts` (TOFU, keyed by the SSH alias, unaffected by tunnel address changes)
- Every subsequent connection (including key tests and public key uploads) verifies against it; a mismatch refuses the connection
- If the host key legitimately changed (e.g., server reinstall), reset it and reconnect:

```bash
cpolar-connect config clear-hostkey
```

Additionally, the first connection tries your existing SSH keys (ssh-agent/default keys) to install the public key automatically — if accepted, no server password is needed at all.

## 📚 Use Cases

### Jupyter Notebook
```bash
# Configure port 8888
cpolar-connect config set server.ports 8888

# Access locally after connection
# http://localhost:8888
```

### Multiple Port Forwarding
```bash
# Configure multiple ports
cpolar-connect config set server.ports 8888,6006,3000

# After connection:
# localhost:8888 -> server:8888 (Jupyter)
# localhost:6006 -> server:6006 (TensorBoard)
# localhost:3000 -> server:3000 (Web App)
```

### SSH Alias Quick Connect
```bash
# After successful connection, use alias
ssh cpolar-server
```

## 🔔 Scope & Limitations

- Supported Plan: Currently supports and is validated on the cpolar Free plan. The tool relies on the assumption that tunnel addresses rotate periodically, then fetches the latest address and updates SSH config accordingly.
- Subscription Plans: Subscription tiers (e.g., fixed domain, custom domain, dedicated tunnels, multi-tunnel) are not validated and are out of the intended scope. Behavior may be unexpected and is not guaranteed.

## 📁 File Locations

- Configuration: `~/.cpolar_connect/config.json`
- Password File: `~/.cpolar_connect/.password` (mode 600)
- Host Keys: `~/.cpolar_connect/known_hosts`
- SSH Key: `~/.ssh/id_rsa_cpolar`
- Log File: `~/.cpolar_connect/logs/cpolar.log`

## 🏥 Diagnostic Tool

When encountering issues, use the built-in diagnostic tool for quick troubleshooting:

```bash
cpolar-connect doctor
```

| Check Item | Description |
|------------|-------------|
| Configuration | Config file integrity |
| Password | Whether password is saved |
| Network | Network connectivity |
| SSH Keys | Private/public key existence |
| SSH Config | ~/.ssh/config entry |
| Cpolar Auth | Account verification |
| Tunnel Status | Active tunnel detection |

## ❓ FAQ

### Can't connect?
1. Run diagnostics: `cpolar-connect doctor`
2. Check cpolar is running on server: `sudo systemctl status cpolar`
3. Verify username and password are correct
4. View detailed logs: `CPOLAR_LOG_LEVEL=DEBUG cpolar-connect`

### How to uninstall?
```bash
# uv
uv tool uninstall cpolar-connect

# pipx
pipx uninstall cpolar-connect

# pip
pip uninstall cpolar-connect
```

### Which systems are supported?
- ✅ Linux (Ubuntu, CentOS, Debian...)
- ✅ macOS
- ❓  Windows

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📄 License

MIT License - See [LICENSE](LICENSE)

## 🔗 Links

- [cpolar Official Website](https://www.cpolar.com)
- [Server Setup Guide](docs/SERVER_SETUP_en.md)
- [Issue Tracker](https://github.com/Hoper-J/cpolar-connect/issues)

---

<div align="center">
<strong>Thank you for your STAR🌟, hope all of this helps you.</strong>

</div>
