<div align="center">

中文 | [English](./README_en.md)

</div>

- **本仓库基于 cpolar 免费版，提供简单的内网穿透解决方案**。
  - 由于 cpolar 免费版的 `host` 和 `port` 会不定期变更，手动更新信息较为繁琐。本仓库将通过自动化脚本解决这一问题。
- **脚本将自动更新客户端的配置文件，以实现远程访问和免密码 SSH 登录**。具体步骤如下：
  - 登录 cpolar，获取隧道信息。
  - 检测本地 SSH 密钥，如果不存在则自动生成。
  - 上传公钥到远程服务器，实现免密登录。
  - 更新本地 `~/.ssh/config`，简化 SSH 连接配置。
- **目前仅测试在 Mac/Linux 下运行。**

---

## 快速开始

> **关于服务器和客户端的定义**
>
> 为便于理解，假设一个常见场景：「你在家使用笔记本电脑」远程连接到「实验室拥有显卡的台式机」。在本仓库中，远程台式机称为「服务器」，而你的笔记本则称为「客户端」。

<details>
    <summary> <h3> 服务器配置 </h3> </summary>

请根据对应的系统遵循[官方文档](https://www.cpolar.com/docs)进行配置，这里给出 Linux 的配置方式：

1. **安装**

   - 国内：

     ```bash
     curl -L https://www.cpolar.com/static/downloads/install-release-cpolar.sh | sudo bash
     ```

   - 国外：

     ```bash
     curl -sL https://git.io/cpolar | sudo bash
     ```

2. **Token 认证**

   访问 cpolar：[https://dashboard.cpolar.com/signup](https://dashboard.cpolar.com/signup)，先注册好一个账号（无需验证邮箱和手机号），然后进行登录。

   ![登录](https://i-blog.csdnimg.cn/blog_migrate/5525126a4890c9305b47a25620a3569e.png)

   登录 cpolar 官网[后台](https://dashboard.cpolar.com/get-started)，点击左侧的`验证`，查看你的认证 token，之后将 token 贴在命令行里：

   ```bash
   cpolar authtoken xxxxxxx
   ```

   ![authtoken](https://i-blog.csdnimg.cn/blog_migrate/e24196b03a5f25c8bea1b2f2bba20d39.png)

3. **开机自启动**

   执行下列命令让其开机自动进行内网穿透，这样在远程服务器不慎重启时，本机依然可以连接：

   ```bash
   sudo systemctl enable cpolar	# 向系统添加服务
   sudo systemctl start cpolar	# 启动cpolar服务
   sudo systemctl status cpolar	# 查看服务状态
   ```

   显示 `active` 表示成功。

4. **查看当前服务器端的用户名**

   ```bash
   whoami
   ```

   这将在之后的客户端配置文件中被用到。

> **【可选】查看公网地址和端口号（服务器/客户端）**
>
> 你可以通过以下三种方式查看内网穿透状态：
>
> 1. 服务器用浏览器访问 [127.0.0.1:9200](http://127.0.0.1:9200/#/dashboard)，登录本地 cpolar web-ui 管理界面
> 2. 客户端直接访问 [https://dashboard.cpolar.com/status](https://dashboard.cpolar.com/status)，查看隧道名为 `ssh` 对应的 URL。
> 3. 直接运行 script.py（位于客户端部分）。
>
> **示例：**
>
> - URL：`tcp://3.tcp.vip.cpolar.cn:10387`
> - 公网地址：`3.tcp.vip.cpolar.cn`
> - 端口号：`10387`

</details>

### 客户端配置

1. **克隆仓库**

   ```bash
   git clone https://github.com/Hoper-J/QuickTunnel
   cd QuickTunnel
   ```

2. **配置文件**

   将 cpolar 的账号/密码以及服务器端的用户名（通过 `whoami` 获取）填充至配置文件 `config.txt` 中：

   ```txt
   # Please fill in the details correctly
   cpolar_username = your_cpolar_username
   cpolar_password = your_cpolar_password
   server_user     = your_server_user
   
   # Custom settings
   ports           = 8888, 6666
   auto_connect    = True
   
   # The following settings can be left as is
   server_password = 
   ssh_key_path    = ~/.ssh/id_rsa_server
   ssh_host_alias  = server
   ```

   **参数说明**

   - `cpolar_username` / `cpolar_password`：cpolar 平台的登录账号和密码。
   - `server_user` / `server_password`：远程服务器的 SSH 用户名和密码，密码可以不在配置文件中明文写出，如果不提供，脚本会提示输入。
   - `ports`：需要映射的端口号，默认为 8888 和 6006 端口（多个端口号之间需要使用英文逗号 "," 隔开）。
   - `auto_connect`：决定运行脚本后是否自动连接到服务器，默认为 `True`，运行脚本后自动连接到服务器。设置为 `False` 则不自动连接。
   - `ssh_key_path`：SSH 私钥的存储路径，如果不存在该私钥则自动创建到该路径。
   - `ssh_host_alias`：本地 SSH 配置的别名，用于简化连接命令。

3. **环境配置**

   在运行脚本之前，需要满足以下依赖：

   - `requests`
   - `beautifulsoup4`
   - `paramiko`

   命令行执行：

   ```bash
   pip install requests beautifulsoup4 paramiko
   ```

4. **运行脚本**

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

## 题外话

需要特别说明的是，当前脚本并非即开即用的完整解决方案，其使用依赖以下两个前提条件：

1. 服务器端已成功配置 **cpolar**。
2. 客户端环境中已安装 **Python**。

> 目前尚未开发适配的 Shell 脚本。本脚本最初是为了应对个人需求而编写，现在整理分享出来供大家参考和使用。