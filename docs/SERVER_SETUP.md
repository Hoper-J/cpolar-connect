# 服务器配置指南

本指南将帮助您在服务器上配置 cpolar 内网穿透服务，用于 SSH 远程连接。

## 📋 前置要求

- 一台运行 Linux/Windows/macOS 的服务器
- cpolar 账号（免费版即可）
- SSH 服务已启动

## 🐧 Linux 服务器配置

### 1. 安装 cpolar

国内用户：
```bash
curl -L https://www.cpolar.com/static/downloads/install-release-cpolar.sh | sudo bash
```

国外用户：
```bash
curl -sL https://git.io/cpolar | sudo bash
```

### 2. Token 认证

1. 访问 cpolar：https://dashboard.cpolar.com/signup 注册账号（无需验证邮箱和手机号）

   ![登录](https://i-blog.csdnimg.cn/blog_migrate/5525126a4890c9305b47a25620a3569e.png)

2. 登录后访问：https://dashboard.cpolar.com/auth 查看您的认证 token

   ![authtoken](https://i-blog.csdnimg.cn/blog_migrate/e24196b03a5f25c8bea1b2f2bba20d39.png)

3. 在服务器执行：

```bash
cpolar authtoken YOUR_AUTH_TOKEN_HERE
```

### 3. 配置开机自启动

执行以下命令让 cpolar 开机自动进行内网穿透：

```bash
sudo systemctl enable cpolar   # 向系统添加服务
sudo systemctl start cpolar    # 启动cpolar服务
sudo systemctl status cpolar   # 查看服务状态
```

显示 `active` 表示成功。

> [!note]
>
> 在 AutoDL 这样的服务器上无法启动该配置，每次启动服务器的时候需要手动执行服务启动的命令，比如 `cpolar tcp 22`。

### 4. 查看服务器用户名

记录下当前用户名，客户端配置时需要使用：

```bash
whoami
```

## 🪟 Windows 服务器配置

### 1. 下载安装

从 [cpolar 官网](https://www.cpolar.com/downloads) 下载 Windows 版本并安装。

### 2. 认证配置

打开命令提示符或 PowerShell，执行：

```cmd
cpolar authtoken YOUR_AUTH_TOKEN_HERE
```

### 3. 安装服务

```cmd
cpolar service install
cpolar service start
```

## 🍎 macOS 服务器配置

### 1. 安装 cpolar

使用 Homebrew：
```bash
brew tap probezy/cpolar
brew install cpolar
```

或直接下载：
```bash
curl -sL https://git.io/cpolar | sudo bash
```

### 2. 认证配置

```bash
cpolar authtoken YOUR_AUTH_TOKEN_HERE
```

### 3. 启动服务

```bash
# 临时启动
cpolar tcp 22

# 后台运行
nohup cpolar tcp 22 &
```

## ✅ 验证配置

### 查看隧道状态

您可以通过以下方式验证配置是否成功：

1. **服务器本地查看**：
   浏览器访问 http://127.0.0.1:9200/#/status

2. **在线控制台查看**：
   登录 https://dashboard.cpolar.com/status
   
   查看名为 `ssh` 的隧道，会显示类似这样的地址：
   - URL: `tcp://3.tcp.vip.cpolar.cn:10387`
   - 公网地址: `3.tcp.vip.cpolar.cn`
   - 端口号: `10387`

3. **命令行查看**：
   ```bash
   cpolar status
   ```

## ❓ 常见问题

### Q: cpolar 免费版有什么限制？

- 隧道地址会不定期变化（24小时重置）
- 这正是 cpolar-connect 工具要解决的问题 - 自动获取最新地址

### Q: 如何确保 SSH 安全？

1. 使用强密码
2. cpolar-connect 会自动配置 SSH 密钥认证
3. 考虑修改 SSH 默认端口（需同步修改 cpolar 配置）

### Q: 服务器重启后需要手动操作吗？

不需要。配置 systemctl 自启动后，服务器重启会自动启动 cpolar 服务。

---

## 下一步

服务器配置完成后，在客户端安装 cpolar-connect：

### 使用 uv（推荐）

```bash
# Linux/macOS 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows 安装 uv (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 运行 cpolar-connect
uvx cpolar-connect
```

### 或使用 pipx

```bash
pipx install cpolar-connect
```

然后运行 `cpolar-connect init` 进行初始化配置即可！

