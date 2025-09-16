# Cpolar Connect

<div align="center">

[![PyPI version](https://img.shields.io/pypi/v/cpolar-connect.svg)](https://pypi.org/project/cpolar-connect/)
[![Python](https://img.shields.io/pypi/pyversions/cpolar-connect.svg)](https://pypi.org/project/cpolar-connect/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

中文 | [English](./README_en.md)

**🚀 自动化管理 cpolar 内网穿透连接的命令行工具**

</div>

## ✨ 为什么需要这个工具？

cpolar 免费版的隧道地址会时不时重置，每次都需要：
1. 登录 cpolar 网站查看新地址
2. 手动更新 SSH 配置
3. 记住新的端口号

**Cpolar Connect 会解决这些问题。**

## 🎯 主要特性

- 🔄 **自动更新**: 自动获取最新的 cpolar 隧道地址
- 🔐 **安全存储**: 密码加密保存，支持系统密钥环
- 🌏 **双语支持**: 中英文界面智能切换
- ⚡ **一键连接**: 无需记忆地址和端口
- 🔑 **SSH 密钥**: 自动配置免密登录
- 📦 **简单安装**: 一行命令即可使用

## 📦 安装方法

### 方式一：使用 uv（推荐，最快）

首先安装 uv：

**Linux/macOS:**
```bash
# 使用官方安装脚本
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或使用 pip
pip install uv
```

**Windows:**
```powershell
# 使用 PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用 pip
pip install uv
```

然后运行 cpolar-connect：
```bash
# 直接运行（无需安装）
uvx cpolar-connect

# 或安装到系统
uv tool install cpolar-connect
```

### 方式二：使用 pipx（独立环境）

```bash
# 安装
pipx install cpolar-connect

# 升级
pipx upgrade cpolar-connect
```

### 方式三：使用 pip

```bash
pip install cpolar-connect
```

## 🚀 快速开始

### 服务器端配置

> 服务器需要先安装并运行 cpolar，详见 [服务器配置指南](docs/SERVER_SETUP.md)

快速配置（Linux）：
```bash
# 1. 安装 cpolar
curl -L https://www.cpolar.com/static/downloads/install-release-cpolar.sh | sudo bash

# 2. 配置认证（需要先注册 cpolar 账号）
cpolar authtoken YOUR_TOKEN

# 3. 设置开机自启
sudo systemctl enable cpolar
sudo systemctl start cpolar

# 4. 查看用户名（客户端配置需要）
whoami
```

### 客户端配置

#### 1️⃣ 初始化配置

```bash
cpolar-connect init
```

根据提示输入：
- 📧 cpolar 用户名（邮箱）
- 👤 服务器用户名（上面 whoami 的结果）
- 🔌 要转发的端口（默认 8888,6666）
- 🔑 是否保存密码（推荐）

#### 2️⃣ 连接服务器

```bash
# 直接连接
cpolar-connect

# 或使用环境变量提供密码
CPOLAR_PASSWORD=your_password cpolar-connect
```

**就这么简单！** 工具会自动：
- ✅ 登录 cpolar 获取最新地址
- ✅ 生成 SSH 密钥（首次）
- ✅ 配置免密登录
- ✅ 建立连接并转发端口

## ⚙️ 配置管理

### 查看配置
```bash
cpolar-connect config show
```

### 修改配置
```bash
# 修改服务器用户
cpolar-connect config set server.user ubuntu

# 修改端口
cpolar-connect config set server.ports 8080,3000

# 直接编辑配置文件
cpolar-connect config edit
```

### 切换语言
```bash
# 中文
cpolar-connect language zh

# English
cpolar-connect language en
```

### 查看状态
```bash
cpolar-connect status
```
显示当前隧道地址、主机/端口、SSH 别名与本地转发配置（不发起连接）。

## 🔒 密码管理

### 选项 1：环境变量（推荐）
```bash
export CPOLAR_PASSWORD=your_password
cpolar-connect
```
**优点**：不需要系统权限，不会触发 macOS 钥匙串权限提示。

### 选项 2：系统密钥环（最安全）
初始化时选择保存密码，将安全存储在系统密钥环中。

> **macOS 用户注意**：首次访问钥匙串时，系统会提示授权。请选择“始终允许”以避免重复提示。

### 选项 3：每次输入
不保存密码，每次连接时输入。

## 📚 使用场景

### Jupyter Notebook
```bash
# 配置端口 8888
cpolar-connect config set server.ports 8888

# 连接后本地访问
# http://localhost:8888
```

### 多端口转发
```bash
# 配置多个端口
cpolar-connect config set server.ports 8888,6006,3000

# 连接后：
# localhost:8888 -> 服务器:8888 (Jupyter)
# localhost:6006 -> 服务器:6006 (TensorBoard)  
# localhost:3000 -> 服务器:3000 (Web App)
```

## 🔔 适用范围与限制

- 支持的套餐：当前仅支持并在 cpolar 免费套餐（Free）下验证。该工具依赖“隧道地址会周期性重置”的前提来获取最新地址并更新 SSH 配置。
- 订阅套餐：订阅套餐（如固定域名、自定义域名、专属隧道、多隧道等）未在本工具中做兼容性验证，行为未预期

### SSH 别名快速连接
```bash
# 连接成功后，可使用别名
ssh cpolar-server
```

## 📁 文件位置

- 配置文件：`~/.cpolar_connect/config.json`
- SSH 密钥：`~/.ssh/id_rsa_cpolar`
- 日志文件：`~/.cpolar_connect/logs/cpolar.log`

## 🏥 诊断工具

遇到问题时，使用内置诊断工具快速定位：

```bash
cpolar-connect doctor
```

这会检查：
- ✅ 配置文件完整性
- ✅ 网络连接状态
- ✅ Cpolar 认证
- ✅ SSH 密钥和配置
- ✅ 活动隧道状态

输出示例：
```
🏥 诊断结果
┏━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ 检查项         ┃ 状态   ┃ 详情             ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ 配置文件       │ ✅ OK  │ 配置有效         │
│ 网络连接       │ ✅ OK  │ 网络连接正常     │
│ Cpolar 认证    │ ✅ OK  │ 成功认证 cpolar  │
│ 隧道状态       │ ⚠️ WARN │ 没有活动隧道     │
└────────────────┴────────┴──────────────────┘
```

## ❓ 常见问题

### 无法连接？
1. 运行诊断：`cpolar-connect doctor`
2. 确认服务器 cpolar 正在运行：`sudo systemctl status cpolar`
3. 确认用户名密码正确
4. 查看详细日志：`CPOLAR_LOG_LEVEL=DEBUG cpolar-connect`

### 如何卸载？
```bash
# uv
uv tool uninstall cpolar-connect

# pipx
pipx uninstall cpolar-connect

# pip
pip uninstall cpolar-connect
```

### 支持哪些系统？
- ✅ Linux (Ubuntu, CentOS, Debian...)
- ✅ macOS
- ❓  Windows

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE)

## 🔗 相关链接

- [cpolar 官网](https://www.cpolar.com)
- [服务器配置指南](docs/SERVER_SETUP.md)
- [问题反馈](https://github.com/Hoper-J/cpolar-connect/issues)

---

<div align="center">
    <strong>感谢你的STAR🌟，希望这一切对你有所帮助。</strong>


</div>
