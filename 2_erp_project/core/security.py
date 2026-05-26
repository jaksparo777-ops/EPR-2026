from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages

def require_role(roles):
    """
    Decorator that restricts view access to users belonging to specific groups.
    Superusers and staff members always have access.
    """
    if isinstance(roles, str):
        roles = [roles]
        
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            # Superusers and admin staff bypass role check
            if request.user.is_superuser or request.user.is_staff:
                return view_func(request, *args, **kwargs)
                
            # Check group membership
            user_groups = request.user.groups.values_list('name', flat=True)
            if any(role in user_groups for role in roles):
                return view_func(request, *args, **kwargs)
                
            messages.error(request, "Access Denied: You do not have permission to access that section.")
            return redirect('dashboard')
            
        return _wrapped_view
    return decorator
