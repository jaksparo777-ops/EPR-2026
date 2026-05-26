def user_roles(request):
    """
    Context processor to inject boolean flags for user roles/groups
    globally into the template rendering context.
    """
    user = request.user
    if not user.is_authenticated:
        return {
            'is_system_admin': False,
            'is_production_operator': False,
            'is_logistics_supervisor': False,
            'is_hr_manager': False,
        }
    
    is_admin = user.is_superuser or user.is_staff or user.groups.filter(name='System Admin').exists()
    
    return {
        'is_system_admin': is_admin,
        'is_production_operator': is_admin or user.groups.filter(name='Production Operator').exists(),
        'is_logistics_supervisor': is_admin or user.groups.filter(name='Logistics Supervisor').exists(),
        'is_hr_manager': is_admin or user.groups.filter(name='HR & Accounts Manager').exists(),
    }
