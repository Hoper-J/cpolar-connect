"""
Shared fixtures for cpolar-connect tests.

HTML samples are based on actual cpolar dashboard pages.
"""

import socket
import sys
import threading
from pathlib import Path

import paramiko
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

from cpolar_connect import i18n, ssh


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "posix_only: relies on POSIX permission bits or shells; skipped on Windows",
    )


def pytest_collection_modifyitems(config, items):
    if sys.platform != "win32":
        return
    skip = pytest.mark.skip(reason="POSIX permission bits/shells; not on Windows")
    for item in items:
        if "posix_only" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path: Path):
    """Keep the developer's home, accounts, ssh-agent and locale out of every test.

    The i18n singleton latches its language on first use (and reads the real
    ~/.cpolar_connect config to do so); it is reset per test and pinned to
    English, so message assertions hold for any test order or developer setup.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # os.path.expanduser("~/...") reads these instead of Path.home()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("CPOLAR_LANG", "en")
    for var in (
        "CPOLAR_ACCOUNT",
        "CPOLAR_PASSWORD",
        "CPOLAR_LOG_LEVEL",
        "SSH_AUTH_SOCK",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(i18n, "_i18n", None)
    # `ssh -G` reads the real ~/.ssh/config whatever HOME says
    monkeypatch.setattr(ssh, "_ssh_offers_agent_keys", lambda user, host, port: True)


@pytest.fixture
def write_private_key():
    """write(path, kind="ed25519", passphrase=b"", pkcs8=False) puts a private
    key file there, as ssh-keygen writes it (OpenSSH format) or as openssl
    does (PKCS#8), readable by its owner only. Returns the key."""

    def write(path: Path, kind: str = "ed25519", passphrase: bytes = b"", pkcs8=False):
        key = {
            "rsa": lambda: rsa.generate_private_key(65537, key_size=2048),
            "ed25519": ed25519.Ed25519PrivateKey.generate,
            "ecdsa": lambda: ec.generate_private_key(ec.SECP256R1()),
        }[kind]()
        encryption = (
            serialization.BestAvailableEncryption(passphrase)
            if passphrase
            else serialization.NoEncryption()
        )
        key_format = (
            serialization.PrivateFormat.PKCS8
            if pkcs8
            else serialization.PrivateFormat.OpenSSH
        )
        path.write_bytes(
            key.private_bytes(serialization.Encoding.PEM, key_format, encryption)
        )
        # On Windows the mode says nothing; there it takes an access list
        ssh._restrict_to_user(path)
        return key

    return write


class LoopbackServer(paramiko.ServerInterface):
    """Accepts the password "right" and remembers every password it is sent.

    With accept_commands it also takes commands to run, and then says nothing
    more: what a server looks like once the connection to it has gone dead.
    """

    def __init__(self, accept_commands=False):
        self.passwords = []
        self.commands = []
        self._accept_commands = accept_commands

    def get_allowed_auths(self, username):
        return "password"

    def check_auth_password(self, username, password):
        self.passwords.append(password)
        if password == "right":
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        if self._accept_commands and kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel, command):
        self.commands.append(command.decode("utf-8", errors="replace"))
        return self._accept_commands


@pytest.fixture
def ssh_server():
    """Start real SSH servers on the loopback interface, each with the host
    keys it is given: start(keys, accept_commands=False) -> (port, the
    server's LoopbackServer)."""
    listeners, transports = [], []

    def start(host_keys, accept_commands=False):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(5)
        listeners.append(listener)
        interface = LoopbackServer(accept_commands)

        def serve():
            while True:
                try:
                    connection, _address = listener.accept()
                except OSError:
                    return  # closed by the teardown
                transport = paramiko.Transport(connection)
                transports.append(transport)
                for key in host_keys:
                    transport.add_server_key(key)
                try:
                    transport.start_server(server=interface)
                except Exception:
                    pass  # a client that walks away is part of the tests

        threading.Thread(target=serve, daemon=True).start()
        return listener.getsockname()[1], interface

    yield start
    for listener in listeners:
        listener.close()
    for transport in transports:
        transport.close()


@pytest.fixture
def sample_status_html():
    """Real cpolar status page HTML with tunnel table."""
    return """
<table class="table table-sm">
 <thead>
  <tr>
   <th scope="col">隧道名称</th>
   <th scope="col">URL</th>
   <th scope="col">地区</th>
   <th scope="col">本地地址</th>
   <th scope="col">创建时间</th>
  </tr>
 </thead>
 <tbody>
  <tr>
   <td>default</td>
   <th scope="row">
    <a href="#ZgotmplZ" target="_blank">tcp://7.tcp.vip.cpolar.cn:12766</a>
   </th>
   <td>cn_vip</td>
   <td>tcp://127.0.0.1:22</td>
   <td>2026-01-28 09:51:32 +0800 CST</td>
  </tr>
  <tr>
   <td>website</td>
   <th scope="row">
    <a href="http://4cbb1683.r35.cpolar.top" target="_blank">http://4cbb1683.r35.cpolar.top</a>
   </th>
   <td>cn_top</td>
   <td>http://localhost:8080</td>
   <td>2026-01-28 10:03:51 +0800 CST</td>
  </tr>
  <tr>
   <td>remoteDesktop</td>
   <th scope="row">
    <a href="#ZgotmplZ" target="_blank">tcp://35.tcp.cpolar.top:12211</a>
   </th>
   <td>cn_top</td>
   <td>tcp://127.0.0.1:3389</td>
   <td>2026-01-28 10:03:53 +0800 CST</td>
  </tr>
 </tbody>
</table>
"""


@pytest.fixture
def sample_status_html_only_remote_desktop():
    """Status page with only remoteDesktop tunnel (no SSH)."""
    return """
<table class="table table-sm">
 <thead>
  <tr>
   <th scope="col">隧道名称</th>
   <th scope="col">URL</th>
   <th scope="col">地区</th>
   <th scope="col">本地地址</th>
   <th scope="col">创建时间</th>
  </tr>
 </thead>
 <tbody>
  <tr>
   <td>remoteDesktop</td>
   <th scope="row">
    <a href="#ZgotmplZ" target="_blank">tcp://35.tcp.cpolar.top:12211</a>
   </th>
   <td>cn_top</td>
   <td>tcp://127.0.0.1:3389</td>
   <td>2026-01-28 10:03:53 +0800 CST</td>
  </tr>
 </tbody>
</table>
"""


@pytest.fixture
def sample_login_form_html():
    """Real cpolar login form HTML."""
    return """
<form action="/login" id="captcha-form" method="POST">
 <fieldset>
  <div class="control-group">
   <label class="control-label" for="email">
    <span>邮箱</span>
   </label>
   <div class="controls">
    <div class="controls">
     <input class="input-block-level" name="login" placeholder="邮箱地址" required="" type="email" value=""/>
    </div>
   </div>
  </div>
  <div class="control-group">
   <label class="control-label" for="password">
    <span>密码</span>
   </label>
   <div class="controls">
    <input class="input-block-level" id="password" maxlength="20" name="password" placeholder="密码" required="" type="password" value=""/>
   </div>
  </div>
 </fieldset>
 <input name="csrf_token" type="hidden" value="1538662349.68##b5aa35f374452a6198004dab20d88b13583c7c2c"/>
 <div>
  <button class="btn btn-primary btn-large" id="loginBtn" type="submit">登 录</button>
 </div>
</form>
"""


@pytest.fixture
def sample_login_success_html():
    """Real cpolar page after successful login (get-started page)."""
    return """
<html>
<head><title>cpolar - get started</title></head>
<body>
<ul class="nav nav-pills pull-right" data-logout-url="/logout" data-user-email="user@example.com" id="user-menu">
 <li class="pull-right dropdown">
  <a class="dropdown-toggle" href="#" id="user-menu-link">
   user@example.com
   <span class="caret"></span>
  </a>
  <ul class="dropdown-menu">
   <li><a href="/user">用户设置</a></li>
   <li class="divider"></li>
   <li><a href="/logout">登出</a></li>
  </ul>
 </li>
</ul>
<div class="container">
 <h2>Get Started</h2>
 <p>Welcome to cpolar dashboard</p>
</div>
</body>
</html>
"""


@pytest.fixture
def sample_login_failed_html():
    """Real cpolar login page with error message."""
    return """
<html>
<head><title>cpolar - login</title></head>
<body>
<div class="row-fluid" id="login">
 <div class="span4 offset4">
  <h2 class="first">登 录</h2>
  <div class="alert alert-error">
   The email or password you entered is not valid.
  </div>
  <form action="/login" id="captcha-form" method="POST">
   <fieldset>
    <div class="control-group">
     <input class="input-block-level" name="login" placeholder="邮箱地址" type="email" value=""/>
    </div>
    <div class="control-group">
     <input class="input-block-level" name="password" placeholder="密码" type="password" value=""/>
    </div>
   </fieldset>
   <input name="csrf_token" type="hidden" value="new_csrf_token_456"/>
   <button class="btn btn-primary" type="submit">登 录</button>
  </form>
 </div>
</div>
</body>
</html>
"""


@pytest.fixture
def sample_status_page_full_html():
    """Full status page HTML with navigation and tunnel table."""
    return """
<html>
<head><title>cpolar - status</title></head>
<body>
<ul class="nav nav-pills pull-right" id="user-menu">
 <li class="dropdown">
  <a href="/logout">登出</a>
 </li>
</ul>
<div class="container">
 <h2>隧道状态</h2>
 <table class="table table-sm">
  <thead>
   <tr>
    <th scope="col">隧道名称</th>
    <th scope="col">URL</th>
    <th scope="col">地区</th>
    <th scope="col">本地地址</th>
    <th scope="col">创建时间</th>
   </tr>
  </thead>
  <tbody>
   <tr>
    <td>ssh</td>
    <th scope="row">
     <a href="#ZgotmplZ" target="_blank">tcp://7.tcp.vip.cpolar.cn:12766</a>
    </th>
    <td>cn_vip</td>
    <td>tcp://127.0.0.1:22</td>
    <td>2026-01-28 09:51:32 +0800 CST</td>
   </tr>
  </tbody>
 </table>
</div>
</body>
</html>
"""
