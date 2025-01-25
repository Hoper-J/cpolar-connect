# QuickTunnel: 快速内网穿透

**本项目基于 cpolar 的免费版**，如果你刚好想寻求一个可用的内网穿透方案，可以遵循当前项目。

因为 cpolar 免费版时不时会自动更新 `host` 和 `port`，每天需要重新登陆来手动变更信息，这过于麻烦，在这里你也可以寻求到解决方案。

**目前仅测试在 Mac/Linux 下正确运行。**

## 项目简介

当前项目将自动配置客户端的 cpolar 服务，以实现远程访问和免密码 SSH 登录。具体步骤如下：

- 登录 cpolar，获取隧道信息。
- 检测本地 SSH 密钥，如果不存在则自动生成。
- 上传公钥到远程服务器，实现免密登录。
- 更新本地 `~/.ssh/config`，简化 SSH 连接配置。

## 配置文件

你需要在文件中填充属于你的配置信息。

脚本依赖一个配置文件 `config.txt`：

```txt
# 请正确填充
cpolar_username = your_cpolar_username
cpolar_password = your_cpolar_password
server_user     = your_server_user

# 自定义
ports 			= 8888, 6666
auto_connect    = True

# 以下配置可以不做修改，并不影响最终结果
server_password = 
ssh_key_path    = ~/.ssh/id_rsa_server
ssh_host_alias  = server
```

### 参数说明

- `cpolar_username` / `cpolar_password`：cpolar 平台的登录账号和密码。
- `server_user` / `server_password`：远程服务器的 SSH 用户名和密码，密码可以不在配置文件中明文写出，如果不提供，脚本会提示输入。
- `ports`：需要映射的端口号，默认为 8888 和 6006 端口（多个端口号之间使用 "," 隔开）。
- `auto_connect`：决定运行脚本后是否自动连接到服务器，设置为 `False` 则不自动连接。
- `ssh_key_path`：SSH 私钥的存储路径。
- `ssh_host_alias`：本地 SSH 配置的别名，用于简化连接命令。

## 运行

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

   将自动连接到服务器，`Ctrl+D` 退出。

> **连接服务器（手动）**
>
> 这里取决于你的 `ssh_host_alias`，默认 `ssh_host_alias = server`，此时可以使用以下命令免密登录到服务器：
>
> ```bash
> ssh server
> ```