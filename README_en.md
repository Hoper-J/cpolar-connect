<div align="center">

[中文](./README.md) | English

</div>

- **This repository provides a simple solution for internal network penetration based on the free version of cpolar**.
  - Since the `host` and `port` of the cpolar free version change periodically, manually updating the information can be cumbersome. This repository addresses this issue with automated scripts.
- **The script will automatically update the configuration file on the client to enable remote access and password-free SSH login**. The steps are as follows:
  - Log in to cpolar to obtain tunnel information.
  - Check for local SSH keys, and automatically generate them if they don’t exist.
  - Upload the public key to the remote server to enable password-free login.
  - Update the local `~/.ssh/config` file to simplify SSH connection configurations.
- **Currently tested only on Mac/Linux systems.**

------

## Getting Started

> **Definitions of Server and Client**
>
> To clarify, consider the common scenario: "You are using a laptop at home" to remotely connect to "a desktop with a GPU in the lab." In this repository, the remote desktop is referred to as the "server," and your laptop is referred to as the "client."

<details>
    <summary> <h3> Server Configuration </h3> </summary>

Please refer to the [official documentation](https://www.cpolar.com/docs) for configuration according to your system. Below is the configuration for Linux:

1. **Installation**

   - For users in China:

     ```bash
     curl -L https://www.cpolar.com/static/downloads/install-release-cpolar.sh | sudo bash
     ```

   - For users outside China:

     ```bash
     curl -sL https://git.io/cpolar | sudo bash
     ```

2. **Token Authentication**

   Visit cpolar: https://dashboard.cpolar.com/signup, register for an account (email and phone verification are not required), and log in.

   ![Login](https://i-blog.csdnimg.cn/blog_migrate/5525126a4890c9305b47a25620a3569e.png)

   After logging in to the cpolar [dashboard](https://dashboard.cpolar.com/get-started), click on `验证` on the left menu to find your authentication token. Enter the token in the command line:

   ```bash
   cpolar authtoken xxxxxxx
   ```

   ![Authtoken](https://i-blog.csdnimg.cn/blog_migrate/e24196b03a5f25c8bea1b2f2bba20d39.png)

3. **Enable Auto-Start**

   Run the following commands to configure cpolar to start automatically at boot. This ensures connection even after the remote server restarts:

   ```bash
   sudo systemctl enable cpolar  # Add cpolar to system services
   sudo systemctl start cpolar   # Start cpolar service
   sudo systemctl status cpolar  # Check service status
   ```

   If it displays `active`, the service is running successfully.

4. **Check the Username on the Server**

   ```bash
   whoami
   ```

   This will be used later for the client configuration file.

> **[Optional] Check Public Address and Port Number**
>
> You can verify the status of the network tunneling or port forwarding via:
>
> 1. Use the browser on the server to access [127.0.0.1:9200](http://127.0.0.1:9200/#/dashboard) and log into the local cpolar web UI.
> 2. Visit https://dashboard.cpolar.com/status on the client to find the URL corresponding to the `ssh` tunnel.
> 3. Run `script.py` directly (in the client section).
>
> **Example:**
>
> - URL: `tcp://3.tcp.vip.cpolar.cn:10387`  
>   (This is the full address for accessing the service.)
> - Public Address: `3.tcp.vip.cpolar.cn`  
>   (The public hostname provided by cpolar.)
> - Port Number: `10387`  
>   (The port number for accessing the tunnel.)

</details>

### Client Configuration

1. **Clone the Repository**

   ```bash
   git clone https://github.com/Hoper-J/CpolarAutoUpdater
   cd CpolarAutoUpdater
   ```

2. **Configuration File**

   Fill in your cpolar username/password and the server username (retrieved using `whoami`) in the `config.txt` file:

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

   **Parameter Descriptions**

   - `cpolar_username` / `cpolar_password`: Your cpolar account credentials.
   - `server_user` / `server_password`: The SSH username and password for the remote server. You can leave the password blank; the script will prompt for input if not provided.
   - `ports`: Ports to be mapped. Defaults to `8888` and `6006`. Use commas (`,`) to separate multiple ports.
   - `auto_connect`: Determines whether the script automatically connects to the server after running. Defaults to `True`. Set to `False` to disable automatic connection.
   - `ssh_key_path`: Path for storing the SSH private key. If the key does not exist, it will be automatically created.
   - `ssh_host_alias`: Alias for the SSH host in the client configuration, simplifying connection commands.

3. **Environment Setup**

   Install the following dependencies before running the script:

   - `requests`
   - `beautifulsoup4`
   - `paramiko`

   Execute the following command:

   ```bash
   pip install requests beautifulsoup4 paramiko
   ```

4. **Run the Script**

   ```bash
   python script.py
   ```

   The script will automatically connect to the server. Press `Ctrl+D` to exit.

> **Manually Connect to the Server**
>
> Depending on your `ssh_host_alias` (default: `server`), you can log in to the server without a password using the following command:
>
> ```bash
> ssh server
> ```

## Side Note

It’s important to note that this script is not an out-of-the-box solution and relies on the following prerequisites:

1. **cpolar** has been properly configured on the server side.
2. **Python** is installed on the client side.

> At this stage, no Shell script has been developed. This script was originally created to address personal needs during earlier challenges and is now being shared for others to reference and use.