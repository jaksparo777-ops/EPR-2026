from django.db.models import Q
from apps.authentication.models import Worker, WorkerType

def resolve_worker(worker_id_val):
    """
    Resolves any worker identifier (e.g. 'w_12', 'jw_5', 12, or integer ID)
    into a unified Worker instance.
    """
    if not worker_id_val:
        return None
        
    s_val = str(worker_id_val).strip()
    clean_id = s_val.replace('jw_', '').replace('w_', '')
    return Worker.objects.filter(id=clean_id).first()


def filter_by_worker(queryset, worker_obj=None):
    """
    Filters a StockTransaction, Loan, LaborPayment, or ItemWorkerAllocation queryset
    by unified Worker FK.
    """
    if not worker_obj:
        return queryset.none()
    return queryset.filter(worker=worker_obj)



import re

def parse_user_agent_details(ua_string):
    """
    Parses raw HTTP User-Agent header string into structured metadata:
    Returns dict with device_type, brand_model, os_info, browser_info, default_name, icon.
    """
    if not ua_string or not isinstance(ua_string, str):
        return {
            'device_type': 'DESKTOP',
            'brand_model': 'Computer',
            'os_info': 'Unknown OS',
            'browser_info': 'Browser',
            'default_name': 'Computer (Unknown OS)',
            'icon': '💻'
        }

    ua = ua_string

    # 1. Determine Device Type & Brand
    device_type = 'DESKTOP'
    icon = '💻'
    brand_model = 'Computer'

    if 'iPhone' in ua:
        device_type = 'MOBILE'
        icon = '📱'
        brand_model = 'Apple iPhone'
    elif 'iPad' in ua:
        device_type = 'TABLET'
        icon = '📱'
        brand_model = 'Apple iPad'
    elif 'Android' in ua:
        if 'Mobile' in ua:
            device_type = 'MOBILE'
            icon = '📱'
            brand_model = 'Android Phone'
        else:
            device_type = 'TABLET'
            icon = '📱'
            brand_model = 'Android Tablet'

        # Check common Android manufacturers
        if 'SM-' in ua or 'SAMSUNG' in ua.upper() or 'Samsung' in ua:
            brand_model = 'Samsung Galaxy'
        elif 'Redmi' in ua or 'POCO' in ua or 'Mi ' in ua or 'Xiaomi' in ua:
            brand_model = 'Xiaomi / Redmi'
        elif 'Realme' in ua or 'RMX' in ua:
            brand_model = 'Realme Phone'
        elif 'OnePlus' in ua or 'ONEPLUS' in ua:
            brand_model = 'OnePlus'
        elif 'Pixel' in ua:
            brand_model = 'Google Pixel'
        elif 'Vivo' in ua or 'V2' in ua:
            brand_model = 'Vivo Phone'
        elif 'OPPO' in ua or 'CPH' in ua:
            brand_model = 'OPPO Phone'
    elif 'Macintosh' in ua or 'Mac OS X' in ua:
        device_type = 'DESKTOP'
        icon = '💻'
        brand_model = 'Mac'
    elif 'Windows' in ua:
        device_type = 'DESKTOP'
        icon = '💻'
        brand_model = 'Windows PC'
    elif 'Linux' in ua and 'Android' not in ua:
        device_type = 'DESKTOP'
        icon = '💻'
        brand_model = 'Linux PC'

    # 2. Determine OS Info
    os_info = 'Unknown OS'
    if 'iPhone OS' in ua:
        m = re.search(r'iPhone OS (\d+[_\.]\d+)', ua)
        ver = m.group(1).replace('_', '.') if m else ''
        os_info = f"iOS {ver}".strip()
    elif 'Mac OS X' in ua:
        m = re.search(r'Mac OS X (\d+[_\.]\d+)', ua)
        ver = m.group(1).replace('_', '.') if m else ''
        os_info = f"macOS {ver}".strip()
    elif 'Android' in ua:
        m = re.search(r'Android (\d+[\.\d+]*)', ua)
        ver = m.group(1) if m else ''
        os_info = f"Android {ver}".strip()
    elif 'Windows NT 10.0' in ua:
        os_info = 'Windows 10/11'
    elif 'Windows NT 6.1' in ua:
        os_info = 'Windows 7'
    elif 'Linux' in ua:
        os_info = 'Linux'

    # 3. Determine Browser Info
    browser_info = 'Browser'
    if 'Brave' in ua or 'Brave/' in ua:
        browser_info = 'Brave'
    elif 'Edg/' in ua or 'Edge/' in ua:
        browser_info = 'Edge'
    elif 'Chrome/' in ua and 'Chromium/' not in ua:
        browser_info = 'Chrome'
    elif 'Safari/' in ua and 'Chrome/' not in ua:
        browser_info = 'Safari'
    elif 'Firefox/' in ua:
        browser_info = 'Firefox'

    default_name = f"{brand_model} ({os_info} • {browser_info})".strip()

    is_bot = bool(
        not ua or 
        'curl' in ua.lower() or 
        'python' in ua.lower() or 
        'norton' in ua.lower() or 
        'bot' in ua.lower() or 
        'crawler' in ua.lower() or 
        'spider' in ua.lower() or
        'headless' in ua.lower()
    )

    return {
        'device_type': device_type,
        'brand_model': brand_model,
        'os_info': os_info,
        'browser_info': browser_info,
        'default_name': default_name,
        'icon': icon,
        'is_bot': is_bot
    }


def classify_network_scope(ip_address):
    """
    Classifies IP address into FACTORY_LOCAL or EXTERNAL_REMOTE.
    """
    if not ip_address:
        return 'FACTORY_LOCAL'
    ip_str = str(ip_address).strip()
    if (ip_str.startswith('192.168.') or 
        ip_str.startswith('10.') or 
        ip_str.startswith('172.16.') or 
        ip_str.startswith('172.17.') or 
        ip_str.startswith('172.18.') or 
        ip_str.startswith('172.19.') or 
        ip_str.startswith('172.20.') or 
        ip_str.startswith('172.30.') or 
        ip_str.startswith('172.31.') or 
        ip_str in ('127.0.0.1', '::1', 'localhost')):
        return 'FACTORY_LOCAL'
    return 'EXTERNAL_REMOTE'


def log_system_audit_event(
    user=None,
    device=None,
    ip_address=None,
    event_type='PAGE_VIEW',
    module_name='System',
    object_id=None,
    object_repr=None,
    changes_json=None,
    request_path=None,
    user_agent_summary=None
):
    """
    Helper function to safely record a SystemAuditLog entry.
    """
    try:
        from apps.authentication.models import SystemAuditLog
        network_scope = classify_network_scope(ip_address)
        return SystemAuditLog.objects.create(
            user=user,
            device=device,
            ip_address=ip_address,
            network_scope=network_scope,
            event_type=event_type,
            module_name=module_name,
            object_id=str(object_id) if object_id is not None else None,
            object_repr=str(object_repr)[:255] if object_repr else None,
            changes_json=changes_json,
            request_path=str(request_path)[:255] if request_path else None,
            user_agent_summary=str(user_agent_summary)[:255] if user_agent_summary else None
        )
    except Exception as e:
        import logging
        logging.getLogger('django').error(f"Failed to log system audit event: {e}")
        return None

