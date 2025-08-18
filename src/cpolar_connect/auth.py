"""
Authentication module for Cpolar Connect
"""

import logging
import requests
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from rich.console import Console

from .config import ConfigManager
from .exceptions import AuthenticationError, NetworkError
from .i18n import _

console = Console()
logger = logging.getLogger(__name__)


class CpolarAuth:
    """Handle cpolar authentication"""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize authentication with config manager"""
        self.config_manager = config_manager
        self.config = config_manager.get_config()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.base_url = self.config.base_url
        self.login_url = f"{self.base_url}/login"
        self.status_url = f"{self.base_url}/status"
        self.authenticated = False
    
    def get_csrf_token(self) -> str:
        """Get CSRF token from login page"""
        try:
            response = self.session.get(self.login_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_input = soup.find("input", {"name": "csrf_token"})
            
            if not csrf_input:
                # Try alternative methods
                # Sometimes the token might be in meta tag
                meta_csrf = soup.find("meta", {"name": "csrf-token"})
                if meta_csrf:
                    return meta_csrf.get("content", "")
                
                logger.error("CSRF token not found in login page")
                raise AuthenticationError(_('error.csrf_token_not_found'))
            
            csrf_token = csrf_input.get("value", "")
            if not csrf_token:
                raise AuthenticationError(_('error.csrf_token_empty'))
            
            logger.debug("Successfully obtained CSRF token")
            return csrf_token
            
        except requests.RequestException as e:
            logger.error(f"Network error while getting login page: {e}")
            raise NetworkError(_('error.network', error=e))
        except Exception as e:
            logger.error(f"Error getting CSRF token: {e}")
            raise AuthenticationError(_('error.auth', error=e))
    
    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> requests.Session:
        """
        Login to cpolar and return authenticated session
        
        Args:
            username: Override config username if provided
            password: Override config password if provided
            
        Returns:
            Authenticated requests.Session object
        """
        # Get credentials
        if not username:
            username = self.config.username
        
        if not password:
            password = self.config_manager.get_password(username)
            if not password:
                raise AuthenticationError(_('auth.password_required'))
        
        try:
            # Step 1: Get CSRF token
            console.print(f"[dim]{_('auth.csrf_token')}[/dim]")
            csrf_token = self.get_csrf_token()
            
            # Step 2: Submit login form
            console.print(f"[dim]{_('auth.logging_in', username=username)}[/dim]")
            
            # Try different field names based on what cpolar might expect
            login_data = {
                'login': username,  # or could be 'username' or 'email'
                'password': password,
                'csrf_token': csrf_token
            }
            
            # Debug: log the form fields we're sending (without password)
            logger.debug(f"Login form fields: {list(login_data.keys())}")
            logger.debug(f"Login URL: {self.login_url}")
            
            response = self.session.post(
                self.login_url, 
                data=login_data,
                timeout=10,
                allow_redirects=False  # Handle redirects manually
            )
            
            # Check for redirect (successful login typically redirects)
            if response.status_code in [302, 303]:
                redirect_url = response.headers.get('Location', '')
                logger.debug(f"Login redirected to: {redirect_url}")
                
                # Follow the redirect
                response = self.session.get(
                    redirect_url if redirect_url.startswith('http') else f"{self.base_url}{redirect_url}",
                    timeout=10
                )
                response.raise_for_status()
            else:
                response.raise_for_status()
            
            # Step 3: Verify login success
            if not self._verify_authentication(response):
                logger.error("Login verification failed")
                raise AuthenticationError(_('auth.login_failed'))
            
            self.authenticated = True
            console.print(f"[green]{_('auth.login_success')}[/green]")
            logger.info(f"Successfully authenticated as {username}")
            
            return self.session
            
        except requests.RequestException as e:
            logger.error(f"Network error during login: {e}")
            raise NetworkError(_('error.network', error=e))
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during login: {e}")
            raise AuthenticationError(_('error.auth', error=e))
    
    def _verify_authentication(self, response: requests.Response) -> bool:
        """
        Verify that authentication was successful
        
        Args:
            response: Response from login POST request
            
        Returns:
            True if authentication successful, False otherwise
        """
        response_text = response.text.lower()
        
        # Check for success indicators
        success_indicators = [
            'logout',
            'status',
            'dashboard',
            'tunnel',
            '隧道',  # Chinese for tunnel
            'get-started'  # Cpolar redirect page after login
        ]
        
        # Check for failure indicators (be more specific)
        failure_indicators = [
            'login failed',
            'invalid credentials',
            'incorrect password',
            'authentication failed',
            '登录失败',  # Chinese for login failed
            '密码错误'   # Chinese for wrong password
        ]
        
        # If we find failure indicators, authentication failed
        for indicator in failure_indicators:
            if indicator in response_text:
                logger.debug(f"Found failure indicator: {indicator}")
                return False
        
        # If we find success indicators, authentication succeeded
        for indicator in success_indicators:
            if indicator in response_text:
                logger.debug(f"Found success indicator: {indicator}")
                return True
        
        # Check if we're still on login page
        if '/login' in response.url:
            logger.debug("Still on login page after POST")
            return False
        
        # If redirected to status, dashboard, or get-started, consider it success  
        if any(path in response.url for path in ['/status', '/dashboard', '/get-started']):
            logger.debug(f"Redirected to {response.url}")
            return True
        
        # Default to checking for specific text
        return 'logout' in response_text or 'status' in response_text
    
    def logout(self) -> None:
        """Logout from cpolar"""
        if not self.authenticated:
            return
        
        try:
            logout_url = f"{self.base_url}/logout"
            self.session.get(logout_url, timeout=5)
            self.authenticated = False
            logger.info("Logged out from cpolar")
        except Exception as e:
            # Logout errors are not critical
            logger.debug(f"Error during logout: {e}")
    
    def test_connection(self) -> bool:
        """Test connection to cpolar"""
        try:
            response = self.session.get(self.base_url, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        if not self.authenticated:
            return False
        
        # Try to access status page to verify session is still valid
        try:
            response = self.session.get(self.status_url, timeout=10, allow_redirects=True)
            
            # Check if redirected to login page
            if '/login' in response.url.lower():
                self.authenticated = False
                return False
            
            # Check for authentication indicators in response
            response_text = response.text.lower()
            if response.status_code == 200:
                # Look for indicators we're logged in
                if any(indicator in response_text for indicator in ['logout', 'status', 'tunnel', '隧道']):
                    return True
                # If we see login form elements, we're not authenticated
                if any(indicator in response_text for indicator in ['password', 'login', 'sign in']):
                    self.authenticated = False
                    return False
            
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Authentication check failed: {e}")
            self.authenticated = False
            return False
    
    def get_session(self) -> requests.Session:
        """Get the current session, login if necessary"""
        if not self.is_authenticated():
            self.login()
        return self.session
    
    def __enter__(self):
        """Context manager entry - login"""
        return self.get_session()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - logout"""
        self.logout()