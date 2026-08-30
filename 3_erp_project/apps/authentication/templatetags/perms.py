from django import template

register = template.Library()

@register.filter(name='has_perm')
def has_perm(user, path):
    """
    Usage: {% if request.user|has_perm:'machining.stock.adjust_inventory' %} ... {% endif %}
    """
    if not user or not hasattr(user, 'has_perm_node'):
        return True
    return user.has_perm_node(path)

@register.filter(name='has_module')
def has_module(user, module_name):
    """
    Usage: {% if request.user|has_module:'casting' %} ... {% endif %}
    """
    if not user or not hasattr(user, 'has_module_access'):
        return True
    return user.has_module_access(module_name)

@register.filter(name='can_view_financials')
def can_view_financials(user):
    """
    Usage: {% if request.user|can_view_financials %} ... {% endif %}
    """
    if not user or not hasattr(user, 'can_view_financials'):
        return True
    if user.is_superuser or getattr(user, 'role', '') == 'ADMIN':
        return True
    return getattr(user, 'can_view_financials', True)

@register.filter(name='mask_money')
def mask_money(value, user):
    """
    Usage: {{ total_earnings|mask_money:request.user }}
    Replaces monetary amount with '₹ ***' if user does not have can_view_financials permission.
    """
    if can_view_financials(user):
        if value is None or value == '':
            return '₹0.00'
        try:
            val_float = float(value)
            return f"₹{val_float:,.2f}"
        except (ValueError, TypeError):
            return f"₹{value}"
    return "₹ ***"
