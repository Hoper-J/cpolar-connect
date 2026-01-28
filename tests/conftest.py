"""
Shared fixtures for cpolar-connect tests.

HTML samples are based on actual cpolar dashboard pages.
"""

import pytest
from pathlib import Path


@pytest.fixture
def sample_status_html():
    """Real cpolar status page HTML with tunnel table."""
    return '''
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
'''


@pytest.fixture
def sample_status_html_only_remote_desktop():
    """Status page with only remoteDesktop tunnel (no SSH)."""
    return '''
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
'''


@pytest.fixture
def sample_login_form_html():
    """Real cpolar login form HTML."""
    return '''
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
'''


@pytest.fixture
def sample_login_success_html():
    """Real cpolar page after successful login (get-started page)."""
    return '''
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
'''


@pytest.fixture
def sample_login_failed_html():
    """Real cpolar login page with error message."""
    return '''
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
'''


@pytest.fixture
def sample_status_page_full_html():
    """Full status page HTML with navigation and tunnel table."""
    return '''
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
'''
