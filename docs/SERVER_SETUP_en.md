# Server Setup Guide

This guide will help you configure cpolar intranet penetration service on your server for SSH remote connections.

## 📋 Prerequisites

- A server running Linux/Windows/macOS
- A cpolar account (free version is sufficient)
- SSH service is running

## 🐧 Linux Server Configuration

### 1. Install cpolar

For users in China:
```bash
curl -L https://www.cpolar.com/static/downloads/install-release-cpolar.sh | sudo bash
```

For international users:
```bash
curl -sL https://git.io/cpolar | sudo bash
```

### 2. Token Authentication

1. Visit cpolar: https://dashboard.cpolar.com/signup to register an account (no email or phone verification required)

   ![Login](https://i-blog.csdnimg.cn/blog_migrate/5525126a4890c9305b47a25620a3569e.png)

2. After logging in, visit: https://dashboard.cpolar.com/auth to view your authentication token

   ![authtoken](https://i-blog.csdnimg.cn/blog_migrate/e24196b03a5f25c8bea1b2f2bba20d39.png)

3. Execute on the server:

```bash
cpolar authtoken YOUR_AUTH_TOKEN_HERE
```

### 3. Configure Auto-start

Execute the following commands to enable cpolar to start automatically on boot:

```bash
sudo systemctl enable cpolar   # Add service to system
sudo systemctl start cpolar    # Start cpolar service
sudo systemctl status cpolar   # Check service status
```

Display of `active` indicates success.

### 4. Check Server Username

Record the current username, which will be needed for client configuration:

```bash
whoami
```

## 🪟 Windows Server Configuration

### 1. Download and Install

Download the Windows version from [cpolar official website](https://www.cpolar.com/downloads) and install it.

### 2. Authentication Configuration

Open Command Prompt or PowerShell and execute:

```cmd
cpolar authtoken YOUR_AUTH_TOKEN_HERE
```

### 3. Install Service

```cmd
cpolar service install
cpolar service start
```

## 🍎 macOS Server Configuration

### 1. Install cpolar

Using Homebrew:
```bash
brew tap probezy/cpolar
brew install cpolar
```

Or direct download:
```bash
curl -sL https://git.io/cpolar | sudo bash
```

### 2. Authentication Configuration

```bash
cpolar authtoken YOUR_AUTH_TOKEN_HERE
```

### 3. Start Service

```bash
# Temporary start
cpolar tcp 22

# Background running
nohup cpolar tcp 22 &
```

## ✅ Verify Configuration

### Check Tunnel Status

You can verify the configuration is successful through the following methods:

1. **Server local view**:
   Browser access http://127.0.0.1:9200/#/status

2. **Online console view**:
   Login to https://dashboard.cpolar.com/status
   
   Look for the tunnel named `ssh`, which will display an address like:
   - URL: `tcp://3.tcp.vip.cpolar.cn:10387`
   - Public address: `3.tcp.vip.cpolar.cn`
   - Port number: `10387`

3. **Command line view**:
   ```bash
   cpolar status
   ```

## ❓ Frequently Asked Questions

### Q: What are the limitations of cpolar free version?

- Tunnel addresses change periodically (reset every 24 hours)
- This is exactly the problem cpolar-connect solves - automatically fetching the latest address

### Q: How to ensure SSH security?

1. Use strong passwords
2. cpolar-connect will automatically configure SSH key authentication
3. Consider changing the default SSH port (requires corresponding cpolar configuration change)

### Q: Do I need manual operations after server restart?

No. After configuring systemctl auto-start, the cpolar service will start automatically when the server restarts.

---

## Next Steps

After server configuration is complete, install cpolar-connect on the client:

### Using uv (recommended)

```bash
# Linux/macOS - Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows - Install uv (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Run cpolar-connect
uvx cpolar-connect
```

### Or using pipx

```bash
pipx install cpolar-connect
```

Then run `cpolar-connect init` to initialize the configuration!