from django.shortcuts import redirect
from django.urls import resolve, Resolver404
from apps.master_data.models import LegalEntity

class CompanyScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if not user.is_authenticated:
            return self.get_response(request)

        path = request.path
        
        # Exclude Django Admin, Static, Media, select-company, login and logout urls from interception
        exempt_prefixes = [
            '/admin/',
            '/static/',
            '/media/',
            '/login/',
            '/logout/',
            '/select-company/'
        ]
        
        if any(path.startswith(prefix) for prefix in exempt_prefixes):
            return self.get_response(request)

        allowed_qs = user.get_allowed_companies()
        allowed_count = allowed_qs.count()

        # If user is restricted to exactly ONE company, lock them to it automatically
        if allowed_count == 1 and not (user.is_superuser or user.role == 'ADMIN' or user.is_global_access):
            comp = allowed_qs.first()
            request.company = comp
            request.session['active_company_id'] = comp.id
            return self.get_response(request)

        # Multi-company or Global user: check active session company selection
        active_company_id = request.session.get('active_company_id')
        if not active_company_id:
            if hasattr(user, 'company') and user.company:
                first_comp = user.company
            else:
                first_comp = allowed_qs.first()

            if first_comp:
                active_company_id = first_comp.id
                request.session['active_company_id'] = first_comp.id
            elif user.is_superuser or user.role == 'ADMIN' or user.is_global_access:
                active_company_id = 'global'
                request.session['active_company_id'] = 'global'
            else:
                return redirect('select_company')

        if active_company_id == 'global':
            if user.is_superuser or user.role == 'ADMIN' or user.is_global_access:
                request.company = None
                return self.get_response(request)
            else:
                # User does NOT have Global access; reset to their first allowed company
                first_comp = allowed_qs.first()
                if first_comp:
                    request.session['active_company_id'] = first_comp.id
                    request.company = first_comp
                    return self.get_response(request)
                return redirect('select_company')

        try:
            cid = int(active_company_id)
            if user.can_access_company(cid):
                request.company = LegalEntity.objects.get(id=cid)
                return self.get_response(request)
            else:
                # Active company ID is not in allowed companies for this user
                first_comp = allowed_qs.first()
                if first_comp:
                    request.session['active_company_id'] = first_comp.id
                    request.company = first_comp
                    return self.get_response(request)
                return redirect('select_company')
        except (ValueError, LegalEntity.DoesNotExist):
            if 'active_company_id' in request.session:
                del request.session['active_company_id']
            return redirect('select_company')


class PermissionEnforcementMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated or request.user.is_superuser or getattr(request.user, 'role', '') == 'ADMIN':
            return self.get_response(request)

        path = request.path

        exempt_prefixes = [
            '/admin/',
            '/static/',
            '/media/',
            '/login/',
            '/logout/',
            '/select-company/',
            '/api/'
        ]
        if any(path.startswith(prefix) for prefix in exempt_prefixes):
            return self.get_response(request)

        # Route to module mapping
        route_map = [
            ('/casting-stock/', 'casting'),
            ('/casting/', 'casting'),
            ('/machined-stock/', 'machining'),
            ('/issue-machining/', 'machining'),
            ('/machining/', 'machining'),
            ('/polished-stock/', 'polishing'),
            ('/polishing/', 'polishing'),
            ('/ready-stock/', 'packaging'),
            ('/packaging/', 'packaging'),
            ('/purchases/', 'purchases'),
            ('/orders/', 'orders'),
            ('/dispatch/', 'dispatch'),
            ('/master-data/', 'master_data'),
            ('/ledger/', 'labor_ledger'),
            ('/attendance/', 'attendance'),
            ('/sql-explorer/', 'sql_explorer'),
            ('/users/', 'user_management'),
        ]

        for route_prefix, module_key in route_map:
            if path.startswith(route_prefix):
                if hasattr(request.user, 'has_module_access') and not request.user.has_module_access(module_key):
                    from django.shortcuts import render
                    return render(request, '403.html', {'forbidden_module': module_key.replace('_', ' ').title()}, status=403)
                break

        return self.get_response(request)


import uuid
from apps.authentication.models import AuthorizedDevice

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip

def is_local_factory_ip(ip):
    if not ip or ip in ('127.0.0.1', 'localhost', '::1'):
        return True
    if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.16.') or ip.startswith('172.17.') or ip.startswith('172.18.') or ip.startswith('172.19.'):
        return True
    return False

def get_device_security_mode():
    try:
        from apps.master_data.models import MaintenanceSettings
        ms = MaintenanceSettings.objects.first()
        if ms and ms.device_security_mode:
            return ms.device_security_mode
    except Exception:
        pass
    from django.conf import settings
    if getattr(settings, 'DEBUG', False):
        return 'DEV_AUTO_APPROVE'
    return 'STRICT_SECURITY'

class DeviceSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from apps.authentication.signals import set_current_request, clear_current_request
        set_current_request(request)
        try:
            return self._process_request(request)
        finally:
            clear_current_request()

    def _process_request(self, request):
        path = request.path
        
        # Exempt static assets, admin console, device APIs, and device approval screen
        exempt_prefixes = [
            '/admin/',
            '/static/',
            '/media/',
            '/device-approval-required/',
            '/api/devices/'
        ]
        if any(path.startswith(prefix) for prefix in exempt_prefixes):
            return self.get_response(request)

        sec_mode = get_device_security_mode()
        if sec_mode == 'DISABLED':
            return self.get_response(request)

        client_ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        # Parse user agent details for device identification
        from apps.authentication.utils import parse_user_agent_details
        ua_meta = parse_user_agent_details(user_agent)
        if client_ip in ('127.0.0.1', '::1', 'localhost'):
            if ua_meta['device_type'] != 'DESKTOP':
                ua_meta['device_type'] = 'DESKTOP'
                ua_meta['icon'] = '💻'
                ua_meta['brand_model'] = 'Computer'

        device_token = request.COOKIES.get('device_token')
        new_token_created = False

        if not device_token:
            # Prevent duplicate pending devices from same IP & user agent
            existing_pending = AuthorizedDevice.objects.filter(
                status='PENDING',
                last_ip=client_ip,
                user_agent=user_agent
            ).order_by('-created_at').first()

            if existing_pending:
                device_token = existing_pending.device_id
                device_obj = existing_pending
                created = False
            else:
                device_token = f"DEV-{uuid.uuid4().hex[:8].upper()}"
                new_token_created = True
                created = True
                device_obj = AuthorizedDevice.objects.create(
                    device_id=device_token,
                    name=ua_meta['default_name'],
                    user_agent=user_agent,
                    device_type=ua_meta['device_type'],
                    brand_model=ua_meta['brand_model'],
                    os_info=ua_meta['os_info'],
                    browser_info=ua_meta['browser_info'],
                    last_ip=client_ip,
                    is_approved=False,
                    status='PENDING'
                )
        else:
            # Lookup existing device by cookie token
            device_obj, created = AuthorizedDevice.objects.get_or_create(
                device_id=device_token,
                defaults={
                    'name': ua_meta['default_name'],
                    'user_agent': user_agent,
                    'device_type': ua_meta['device_type'],
                    'brand_model': ua_meta['brand_model'],
                    'os_info': ua_meta['os_info'],
                    'browser_info': ua_meta['browser_info'],
                    'last_ip': client_ip,
                    'is_approved': False,
                    'status': 'PENDING'
                }
            )

        # Check if current mode permits auto-approving this device
        from django.conf import settings
        should_auto_approve = False
        if sec_mode == 'DEV_AUTO_APPROVE':
            if is_local_factory_ip(client_ip) or getattr(settings, 'DEBUG', False):
                should_auto_approve = True
        elif sec_mode == 'FACTORY_LOCAL_AUTO_APPROVE':
            if is_local_factory_ip(client_ip):
                should_auto_approve = True

        if should_auto_approve and (not device_obj.is_approved or device_obj.status != 'APPROVED'):
            device_obj.is_approved = True
            device_obj.status = 'APPROVED'
            device_obj.save(update_fields=['is_approved', 'status'])

        if created and not should_auto_approve:
            # Trigger high-priority System Notification for Admins
            try:
                from apps.master_data.models import Notification
                active_comp = getattr(request, 'company', None)
                notif_title = f"{ua_meta['icon']} New Device Access Request"
                notif_msg = f"Device request from '{ua_meta['brand_model']} ({ua_meta['os_info']})' at IP {client_ip}. Review in Users Manager."
                Notification.objects.create(
                    title=notif_title,
                    message=notif_msg,
                    notification_type='WARNING',
                    link='/users/?tab=devices',
                    company=active_comp
                )
            except Exception:
                pass
        elif device_obj.last_ip != client_ip or device_obj.user_agent != user_agent:
            device_obj.last_ip = client_ip
            device_obj.user_agent = user_agent
            if not device_obj.brand_model or device_obj.name.startswith('Device ') or device_obj.name.startswith('DEV-'):
                device_obj.device_type = ua_meta['device_type']
                device_obj.brand_model = ua_meta['brand_model']
                device_obj.os_info = ua_meta['os_info']
                device_obj.browser_info = ua_meta['browser_info']
                device_obj.name = ua_meta['default_name']
            device_obj.save(update_fields=['last_ip', 'user_agent', 'device_type', 'brand_model', 'os_info', 'browser_info', 'name', 'last_used_at'])

        request.device = device_obj

        # 2. Check Role & Network Exemption for Owner / Super Admin
        user = request.user
        is_owner_admin = user.is_authenticated and (user.is_superuser or getattr(user, 'role', '') == 'ADMIN')

        # Update Live Activity Stream for authenticated users (ignore API requests)
        if user.is_authenticated and not path.startswith('/api/'):
            try:
                from apps.authentication.models import UserLiveActivity
                from apps.authentication.utils import classify_network_scope
                
                page_name = 'Dashboard'
                if path.startswith('/casting') or path.startswith('/casting-stock'): page_name = 'Casting Department'
                elif path.startswith('/machin') or path.startswith('/issue-machining') or path.startswith('/machined-stock'): page_name = 'Machining Department'
                elif path.startswith('/polish') or path.startswith('/polished-stock'): page_name = 'Polishing Department'
                elif path.startswith('/packag') or path.startswith('/ready-stock') or path.startswith('/assembly'): page_name = 'Packaging & Stock'
                elif path.startswith('/purchases'): page_name = 'Purchase Orders'
                elif path.startswith('/orders'): page_name = 'Sales Orders'
                elif path.startswith('/dispatch'): page_name = 'Dispatch & Sales'
                elif path.startswith('/master-data'): page_name = 'Master Data Hub'
                elif path.startswith('/ledger') or path.startswith('/worker'): page_name = 'Labor & HR Ledger'
                elif path.startswith('/attendance'): page_name = 'Attendance Register'
                elif path.startswith('/sql-explorer'): page_name = 'SQL Explorer & Data Flow'
                elif path.startswith('/users'): page_name = 'User Control & Permissions'

                net_scope = classify_network_scope(client_ip)
                UserLiveActivity.objects.update_or_create(
                    user=user,
                    defaults={
                        'device': device_obj,
                        'current_page': page_name,
                        'current_path': path,
                        'ip_address': client_ip,
                        'network_scope': net_scope
                    }
                )
            except Exception:
                pass

        # 3. Network Restrictions for Staff Accounts
        if user.is_authenticated and not is_owner_admin:
            if not is_local_factory_ip(client_ip):
                from apps.authentication.utils import log_system_audit_event
                log_system_audit_event(
                    user=user,
                    device=device_obj,
                    ip_address=client_ip,
                    event_type='SECURITY_BLOCKED',
                    module_name='Security Middleware',
                    object_repr=f'External Network Blocked at IP {client_ip}',
                    request_path=path,
                    user_agent_summary=user_agent
                )
                from django.shortcuts import render
                return render(request, '403_network_restricted.html', {'client_ip': client_ip}, status=403)

        # 4. Device Authorization Token Check (Applies to non-admin staff logins)
        if user.is_authenticated and not is_owner_admin and (not device_obj.is_approved or device_obj.status != 'APPROVED'):
            from apps.authentication.utils import log_system_audit_event
            log_system_audit_event(
                user=user,
                device=device_obj,
                ip_address=client_ip,
                event_type='SECURITY_REJECTED' if device_obj.status == 'REJECTED' else 'SECURITY_BLOCKED',
                module_name='Device Security',
                object_repr=f"Device {device_obj.name} ({device_obj.get_status_display()}) attempted access",
                changes_json={'rejection_reason': device_obj.rejection_reason or ''},
                request_path=path,
                user_agent_summary=user_agent
            )
            from django.shortcuts import render
            response = render(request, 'device_approval_required.html', {
                'device_id': device_token,
                'device_name': device_obj.name,
                'device_status': device_obj.status,
                'rejection_reason': device_obj.rejection_reason or '',
                'next_url': path
            })
            if new_token_created:
                response.set_cookie('device_token', device_token, max_age=365*24*60*60, httponly=False)
            return response

        response = self.get_response(request)
        if new_token_created:
            response.set_cookie('device_token', device_token, max_age=365*24*60*60, httponly=False)
        return response
