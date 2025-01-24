# QuickTunnel: 快速内网穿透

**本项目基于 cpolar 的免费版**，如果你刚好想寻求一个内网穿透的方案，可以遵循当前项目。

免费版的 cpolar 时不时会自动更新 `host` 和 `port`，这导致每天都需要登陆，然后手动变更信息，这过于麻烦，在这里你也可以寻求到解决方案。

## 项目简介

当前项目将帮助你快速配置通过 cpolar 服务实现的远程访问和免密码 SSH 登录。具体步骤如下：

- 登录 cpolar，获取隧道信息。
- 检测本地 SSH 密钥，如果不存在则自动生成。
- 上传公钥到远程服务器，实现免密登录。
- 更新本地 `~/.ssh/config`，简化 SSH 连接配置。

## 配置文件

你需要在文件中填充属于你的配置信息。

脚本依赖一个配置文件 `config.txt`：

```txt
cpolar_username = your_cpolar_username
cpolar_password = your_cpolar_password
server_user     = your_server_user
server_password = 
ssh_key_path    = ~/.ssh/id_rsa_server
ssh_host_alias  = server
```

### 参数说明

- `cpolar_username` / `cpolar_password`：您在 cpolar 平台的登录账号和密码。
- `server_user` / `server_password`：远程服务器的 SSH 用户名和密码，密码可以不在配置文件中明文写出，如果不提供，脚本会提示用户输入。
- **以下两项无需修改**：
  - `ssh_key_path`：SSH 私钥的存储路径。
  - `ssh_host_alias`：本地 SSH 配置的别名，用于简化连接命令。

## 如何运行

1. **克隆项目**

   ```bash
   git clone https://github.com/Hoper-J/QuickTunnel
   cd QuickTunnel
   ```

2. **环境配置**

   在运行脚本之前，需要满足以下依赖：

   - `requests`
   - `beautifulsoup4`
   - `paramiko`

   命令行执行：

   ```bash
   pip install requests beautifulsoup4 paramiko
   ```

3. **运行脚本**

   ```bash
   python script.py
   ```

4. **连接服务器**

   这里取决于你的 `ssh_host_alias`，默认 `ssh_host_alias = server`，此时使用以下命令免密登录到服务器：

   ```bash
   ssh server
   ```

## TODO

- 编写服务器端的配置脚本
- 兼容 Windows 系统
- 完善 README
- 当前脚本仅存在自动更新，还需要在每次连接前调用该脚本（使用 alias）

---

**感谢你的STAR🌟，希望这一切对你有所帮助。**