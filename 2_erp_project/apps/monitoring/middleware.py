import contextvars
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone
from apps.monitoring.models import UserSession

# Thread-safe and async-safe request context variables
_user = contextvars.ContextVar('user', default=None)
_ip = contextvars.ContextVar('ip', default=None)

def get_current_user():
    return _user.get()

def get_current_ip():
    return _ip.get()

def get_client_ip(request):
    """Extracts client IP address handling forward proxy headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def parse_user_agent(ua_string):
    """Fast, dependency-free regex-free user agent string parser."""
    if not ua_string:
        return 'Desktop', 'Unknown', 'Unknown'
    
    ua = ua_string.lower()
    
    # Device Classification
    if 'ipad' in ua or ('android' in ua and 'mobile' not in ua):
        device_type = 'Tablet'
    elif 'mobile' in ua or 'iphone' in ua or 'ipod' in ua:
        device_type = 'Mobile'
    elif 'bot' in ua or 'crawl' in ua or 'spider' in ua or 'slurp' in ua:
        device_type = 'Bot'
    else:
        device_type = 'Desktop'
        
    # Browser Identification
    if 'chrome' in ua or 'crios' in ua:
        browser = 'Chrome'
    elif 'safari' in ua and 'chrome' not in ua:
        browser = 'Safari'
    elif 'firefox' in ua:
        browser = 'Firefox'
    elif 'edge' in ua or 'edg/' in ua:
        browser = 'Edge'
    else:
        browser = 'Other'
        
    # OS Identification
    if 'windows' in ua:
        os = 'Windows'
    elif 'macintosh' in ua or 'mac os x' in ua:
        os = 'macOS'
    elif 'android' in ua:
        os = 'Android'
    elif 'iphone' in ua or 'ipad' in ua or 'ipod' in ua:
        os = 'iOS'
    elif 'linux' in ua:
        os = 'Linux'
    else:
        os = 'Other'
        
    return device_type, browser, os

class MonitoringMiddleware:
    """
    Middleware that captures client device attributes and updates UserSession active timestamps.
    Automatically forces a logout if an active session is terminated from the Admin Monitor Panel.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user if hasattr(request, 'user') else None
        ip = get_client_ip(request)
        
        # Set context variables for background database signals to observe
        user_token = _user.set(user)
        ip_token = _ip.set(ip)
        
        try:
            if user and user.is_authenticated:
                session_key = request.session.session_key
                if session_key:
                    # Check if session is explicitly marked inactive (Force Revocation)
                    db_session = UserSession.objects.filter(session_key=session_key).first()
                    if db_session and not db_session.is_active:
                        logout(request)
                        try:
                            messages.warning(request, "Your session has been terminated by the administrator.")
                        except Exception:
                            pass
                        return redirect('login')
                    
                    # Update or create active session record
                    ua_string = request.META.get('HTTP_USER_AGENT', '')
                    device_type, browser, os = parse_user_agent(ua_string)
                    
                    UserSession.objects.update_or_create(
                        session_key=session_key,
                        defaults={
                            'user': user,
                            'ip_address': ip,
                            'user_agent': ua_string,
                            'device_type': device_type,
                            'browser': browser,
                            'os': os,
                            'last_activity': timezone.now(),
                            'is_active': True
                        }
                    )
            
            response = self.get_response(request)
            return response
        finally:
            # Revert the request context tokens to avoid context leaks
            _user.reset(user_token)
            _ip.reset(ip_token)
