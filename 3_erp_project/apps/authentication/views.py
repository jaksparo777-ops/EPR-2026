import datetime
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q
from apps.master_data.models import LegalEntity
from apps.authentication.models import CustomUser, AuthorizedDevice, SystemAuditLog, UserLiveActivity
from apps.authentication.middleware import get_client_ip

@login_required
def select_company(request):
    user = request.user
    allowed_qs = user.get_allowed_companies()
    can_access_global = user.is_superuser or user.role == 'ADMIN' or user.is_global_access

    # If the user is locked to EXACTLY ONE company and has NO global access, auto-redirect
    if allowed_qs.count() == 1 and not can_access_global:
        comp = allowed_qs.first()
        request.session['active_company_id'] = comp.id
        return redirect('dashboard')

    # Allow switching via GET request (e.g. for one-click redirects from global search)
    if request.method == 'GET' and 'company_id' in request.GET:
        company_id = request.GET.get('company_id')
        next_url = request.GET.get('next', 'dashboard')
        if company_id == 'global' and can_access_global:
            request.session['active_company_id'] = 'global'
            return redirect(next_url)
        elif company_id and str(company_id).isdigit():
            cid = int(company_id)
            if user.can_access_company(cid):
                request.session['active_company_id'] = cid
                return redirect(next_url)

    if request.method == 'POST':
        company_id = request.POST.get('company_id')
        next_url = request.POST.get('next') or request.GET.get('next') or 'dashboard'
        if next_url in ('select_company', '/select-company/'):
            next_url = 'dashboard'
        if company_id == 'global' and can_access_global:
            request.session['active_company_id'] = 'global'
            return redirect(next_url)

        if company_id and str(company_id).isdigit():
            cid = int(company_id)
            if user.can_access_company(cid):
                request.session['active_company_id'] = cid
                return redirect(next_url)

    return render(request, 'select_company.html', {
        'companies': allowed_qs,
        'can_access_global': can_access_global
    })


import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import user_passes_test
from apps.authentication.models import CustomUser

def is_admin_or_superuser(user):
    return user.is_authenticated and (user.is_superuser or getattr(user, 'role', '') == 'ADMIN' or user.has_module_access('user_management'))

def get_default_permission_tree():
    return {
        "casting": {
            "enabled": True,
            "inhouse": {"view": True, "create": True, "edit": True, "delete": True},
            "stock": {"view": True, "adjust_inventory": True}
        },
        "machining": {
            "enabled": True,
            "inhouse": {"view": True, "create": True, "edit": True, "delete": True},
            "outsource": {"view": True, "issue": True, "receive": True},
            "wip": {"view": True},
            "stock": {"view": True, "adjust_inventory": True}
        },
        "polishing": {
            "enabled": True,
            "inhouse": {"view": True, "create": True, "edit": True, "delete": True},
            "outsource": {"view": True, "issue": True, "receive": True},
            "rejection": {"create": True},
            "stock": {"view": True, "adjust_inventory": True}
        },
        "packaging": {
            "enabled": True,
            "entry": {"view": True, "create": True},
            "cartons": {"view": True},
            "ready_stock": {"view": True, "adjust_inventory": True}
        },
        "purchases": {
            "enabled": True,
            "entry": {"view": True, "create": True, "edit": True, "delete": True}
        },
        "orders": {
            "enabled": True,
            "board": {"view": True},
            "create": {"create": True},
            "edit": {"edit": True},
            "delete": {"delete": True}
        },
        "dispatch": {
            "enabled": True,
            "entry": {"view": True, "create": True, "edit": True, "delete": True}
        },
        "master_data": {
            "enabled": True,
            "items": {"view": True, "edit": True, "delete": True},
            "clients": {"view": True, "edit": True, "delete": True},
            "workers": {"view": True, "edit": True, "delete": True},
            "job_workers": {"view": True, "edit": True, "delete": True},
            "bom": {"view": True, "edit": True},
            "rate_matrix": {"view": True, "edit": True},
            "bulk_import": {"view": True, "import": True, "purge": True, "reset": True}
        },
        "labor_ledger": {
            "enabled": True,
            "staff_payroll": {"view": True},
            "jw_ledger": {"view": True},
            "payment": {"create": True, "edit": True, "delete": True},
            "statements": {"view": True}
        },
        "attendance": {
            "enabled": True,
            "view": True,
            "edit": True
        },
        "sql_explorer": {
            "enabled": True,
            "run_query": True
        },
        "user_management": {
            "enabled": True,
            "manage_users": True
        }
    }

@login_required
@user_passes_test(is_admin_or_superuser)
def user_management_view(request):
    users = CustomUser.objects.all().select_related('company').prefetch_related('allowed_companies').order_by('-id')
    companies = LegalEntity.objects.all().order_by('id')
    roles = CustomUser.ROLE_CHOICES
    devices_list = AuthorizedDevice.objects.all().select_related('assigned_user', 'approved_by').order_by('-created_at')
    
    total_users = users.count()
    active_users = users.filter(is_active=True).count()
    admin_users = users.filter(role='ADMIN').count()
    
    total_devices_count = devices_list.count()
    approved_devices_count = devices_list.filter(status='APPROVED').count()
    pending_devices_count = devices_list.filter(status='PENDING').count()
    rejected_devices_count = devices_list.filter(status='REJECTED').count()
    online_devices_count = sum(1 for d in devices_list if d.is_online)
    offline_devices_count = total_devices_count - online_devices_count
    
    current_device_id = getattr(request, 'device', None).device_id if hasattr(request, 'device') and request.device else request.COOKIES.get('device_token', '')
    
    audit_logs_qs = SystemAuditLog.objects.all().select_related('user', 'device').order_by('-timestamp')
    live_activities_list = UserLiveActivity.objects.all().select_related('user', 'device').order_by('-last_heartbeat')[:20]
    
    from apps.authentication.models import AdminRecoveryConfig
    recovery_config = AdminRecoveryConfig.get_config()

    total_audit_logs = audit_logs_qs.count()
    blocked_qs = audit_logs_qs.filter(event_type__in=['SECURITY_BLOCKED', 'SECURITY_REJECTED', 'AUTH_FAILED'])
    if recovery_config.last_security_alerts_cleared_at:
        blocked_qs = blocked_qs.filter(timestamp__gt=recovery_config.last_security_alerts_cleared_at)
    security_blocked_count = blocked_qs.count()
    audit_logs_list = audit_logs_qs[:100]

    from apps.master_data.models import MaintenanceSettings
    m_settings, _ = MaintenanceSettings.objects.get_or_create(id=1)

    is_master_admin = bool(request.user.is_superuser or getattr(request.user, 'role', '') == 'ADMIN')

    context = {
        'users_list': users,
        'companies': companies,
        'roles': roles,
        'devices_list': devices_list,
        'total_users': total_users,
        'active_users': active_users,
        'admin_users': admin_users,
        'total_devices_count': total_devices_count,
        'approved_devices_count': approved_devices_count,
        'pending_devices_count': pending_devices_count,
        'rejected_devices_count': rejected_devices_count,
        'online_devices_count': online_devices_count,
        'offline_devices_count': offline_devices_count,
        'current_device_id': current_device_id,
        'audit_logs_list': audit_logs_list,
        'live_activities_list': live_activities_list,
        'total_audit_logs': total_audit_logs,
        'security_blocked_count': security_blocked_count,
        'now_time': timezone.now(),
        'device_security_mode': m_settings.device_security_mode,
        'security_mode_choices': MaintenanceSettings.SECURITY_MODE_CHOICES,
        'default_permissions_json': json.dumps(get_default_permission_tree()),
        'recovery_config': recovery_config,
        'is_master_admin': is_master_admin,
    }
    return render(request, 'user_management.html', context)

@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def user_create_api(request):
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        role = data.get('role', 'CUSTOM')
        can_view_financials = data.get('can_view_financials', True)
        permissions = data.get('permissions', get_default_permission_tree())
        is_global_access = bool(data.get('is_global_access', False))
        allowed_company_ids = data.get('allowed_company_ids', [])
        
        try:
            session_timeout_minutes = int(data.get('session_timeout_minutes', 60))
        except (ValueError, TypeError):
            session_timeout_minutes = 60
        session_timeout_minutes = max(5, min(480, session_timeout_minutes))
        
        timeout_logout_mode = data.get('timeout_logout_mode', 'POPUP_WARNING')
        if timeout_logout_mode not in ('POPUP_WARNING', 'INSTANT_LOGOUT'):
            timeout_logout_mode = 'POPUP_WARNING'

        if not username or not password:
            return JsonResponse({'status': 'error', 'error': 'Username and Password are required.'}, status=400)

        if CustomUser.objects.filter(username__iexact=username).exists():
            return JsonResponse({'status': 'error', 'error': f'Username "{username}" is already taken.'}, status=400)

        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_global_access=is_global_access,
            can_view_financials=bool(can_view_financials),
            permissions=permissions,
            session_timeout_minutes=session_timeout_minutes,
            timeout_logout_mode=timeout_logout_mode,
            is_staff=True if role in ('ADMIN', 'CASTING_MGR', 'MACHINING_MGR', 'PACKAGING_MGR', 'SALES_ADMIN', 'ACCOUNTANT') else False
        )

        if allowed_company_ids:
            user.allowed_companies.set(LegalEntity.objects.filter(id__in=allowed_company_ids))
            if len(allowed_company_ids) == 1:
                user.company = user.allowed_companies.first()
            else:
                user.company = None
            user.save(update_fields=['company'])

        return JsonResponse({
            'status': 'success',
            'message': f'User account "{user.username}" created successfully.',
            'user_id': user.id
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def user_edit_api(request, user_id):
    try:
        user = CustomUser.objects.get(id=user_id)
        data = json.loads(request.body)
        
        user.first_name = data.get('first_name', user.first_name).strip()
        user.last_name = data.get('last_name', user.last_name).strip()
        user.email = data.get('email', user.email).strip()
        user.role = data.get('role', user.role)
        user.can_view_financials = bool(data.get('can_view_financials', user.can_view_financials))
        if 'is_global_access' in data:
            user.is_global_access = bool(data['is_global_access'])

        if 'session_timeout_minutes' in data:
            try:
                mins = int(data['session_timeout_minutes'])
                user.session_timeout_minutes = max(5, min(480, mins))
            except (ValueError, TypeError):
                pass

        if 'timeout_logout_mode' in data:
            mode = str(data['timeout_logout_mode'])
            if mode in ('POPUP_WARNING', 'INSTANT_LOGOUT'):
                user.timeout_logout_mode = mode

        if 'permissions' in data:
            user.permissions = data['permissions']

        if 'allowed_company_ids' in data:
            comp_ids = data['allowed_company_ids']
            if comp_ids:
                user.allowed_companies.set(LegalEntity.objects.filter(id__in=comp_ids))
                if len(comp_ids) == 1:
                    user.company = user.allowed_companies.first()
                else:
                    user.company = None
            else:
                user.allowed_companies.clear()
                user.company = None

        password = data.get('password', '').strip()
        if password:
            user.set_password(password)

        user.save()

        return JsonResponse({
            'status': 'success',
            'message': f'User "{user.username}" updated successfully.'
        })
    except CustomUser.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

@login_required
@require_POST
def session_keep_alive_api(request):
    """
    Refreshes the session inactivity timestamp when a user interacts or clicks 'Stay Logged In'.
    """
    import time
    now = time.time()
    request.session['last_user_activity'] = now
    return JsonResponse({'status': 'success', 'timestamp': now, 'last_user_activity': now})

@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def user_toggle_active_api(request, user_id):
    try:
        user = CustomUser.objects.get(id=user_id)
        if user == request.user:
            return JsonResponse({'status': 'error', 'error': 'You cannot deactivate your own logged-in account.'}, status=400)
        
        user.is_active = not user.is_active
        user.save()

        return JsonResponse({
            'status': 'success',
            'is_active': user.is_active,
            'message': f'User "{user.username}" is now {"Active" if user.is_active else "Deactivated"}.'
        })
    except CustomUser.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'User not found.'}, status=404)

@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def user_reset_password_api(request, user_id):
    try:
        user = CustomUser.objects.get(id=user_id)
        data = json.loads(request.body)
        new_password = data.get('new_password', '').strip()
        
        if not new_password or len(new_password) < 4:
            return JsonResponse({'status': 'error', 'error': 'Password must be at least 4 characters.'}, status=400)

        user.set_password(new_password)
        user.save()

        return JsonResponse({
            'status': 'success',
            'message': f'Password for user "{user.username}" reset successfully.'
        })
    except CustomUser.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'User not found.'}, status=404)


def device_check_status_api(request):
    device_id = request.GET.get('device_id', '').strip()
    if not device_id:
        return JsonResponse({'is_approved': False, 'status': 'PENDING', 'error': 'Missing device_id'}, status=400)
    
    device = AuthorizedDevice.objects.filter(device_id=device_id).first()
    if not device:
        return JsonResponse({'is_approved': False, 'status': 'PENDING', 'device_id': device_id})

    return JsonResponse({
        'is_approved': (device.status == 'APPROVED'),
        'status': device.status,
        'rejection_reason': device.rejection_reason or '',
        'device_id': device.device_id,
        'name': device.name
    })

@require_POST
def device_register_api(request):
    try:
        data = json.loads(request.body)
        device_id = data.get('device_id', '').strip()
        name = data.get('name', '').strip()

        if not device_id:
            return JsonResponse({'status': 'error', 'error': 'Missing device_id'}, status=400)

        device, created = AuthorizedDevice.objects.get_or_create(
            device_id=device_id,
            defaults={'name': name or f"Device {device_id[-6:]}"}
        )
        if not created and name:
            device.name = name
            device.save(update_fields=['name'])

        return JsonResponse({'status': 'success', 'device_id': device.device_id, 'is_approved': (device.status == 'APPROVED')})
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def device_approve_api(request, device_pk):
    try:
        device = AuthorizedDevice.objects.get(id=device_pk)
        device.is_approved = True
        device.status = 'APPROVED'
        device.rejection_reason = None
        device.approved_by = request.user
        device.approved_at = timezone.now()
        device.save()

        try:
            from apps.master_data.models import Notification
            Notification.objects.filter(link='/users/?tab=devices', is_read=False).update(is_read=True)
        except Exception:
            pass

        return JsonResponse({
            'status': 'success',
            'message': f'Device "{device.name or device.device_id}" approved successfully.'
        })
    except AuthorizedDevice.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'Device not found.'}, status=404)

@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def device_reject_api(request, device_pk):
    try:
        device = AuthorizedDevice.objects.get(id=device_pk)
        reason = ''
        if request.body:
            try:
                data = json.loads(request.body)
                reason = data.get('reason', '').strip()
            except Exception:
                reason = request.POST.get('reason', '').strip()
        else:
            reason = request.POST.get('reason', '').strip()

        device.is_approved = False
        device.status = 'REJECTED'
        device.rejection_reason = reason or 'Declined by Administrator'
        device.save()

        return JsonResponse({
            'status': 'success',
            'message': f'Access for device "{device.name or device.device_id}" has been rejected.'
        })
    except AuthorizedDevice.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'Device not found.'}, status=404)

@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def device_revoke_api(request, device_pk):
    try:
        device = AuthorizedDevice.objects.get(id=device_pk)
        device.is_approved = False
        device.status = 'PENDING'
        device.save()

        return JsonResponse({
            'status': 'success',
            'message': f'Access for device "{device.name or device.device_id}" revoked.'
        })
    except AuthorizedDevice.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'Device not found.'}, status=404)

@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def device_rename_api(request, device_pk):
    try:
        device = AuthorizedDevice.objects.get(id=device_pk)
        data = json.loads(request.body)
        new_name = data.get('name', '').strip()
        user_id = data.get('assigned_user_id')

        if new_name:
            device.name = new_name
        
        if user_id:
            device.assigned_user = CustomUser.objects.filter(id=int(user_id)).first()
        elif user_id == '' or user_id is None:
            device.assigned_user = None

        device.save()

        return JsonResponse({
            'status': 'success',
            'message': f'Device updated successfully.'
        })
    except AuthorizedDevice.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'Device not found.'}, status=404)

@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def device_purge_stale_api(request):
    try:
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=30)
        stale_qs = AuthorizedDevice.objects.filter(is_approved=False, created_at__lt=cutoff)
        count = stale_qs.count()
        stale_qs.delete()

        return JsonResponse({
            'status': 'success',
            'purged_count': count,
            'message': f'Purged {count} stale/unapproved device requests older than 30 days.'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def device_deduplicate_api(request):
    """
    Cleans up redundant duplicate device records created for the same IP, OS, and Browser.
    Also removes bot/scraper/empty user-agent records.
    Keeps the active / approved device with the highest activity (or current device).
    """
    try:
        from apps.authentication.utils import parse_user_agent_details
        current_token = request.COOKIES.get('device_token')
        all_devices = AuthorizedDevice.objects.all().order_by('-is_approved', '-last_used_at', '-created_at')
        seen_keys = {}
        deleted_ids = []

        for dev in all_devices:
            ua = dev.user_agent or ''
            ua_meta = parse_user_agent_details(ua)
            
            # 1. Flag bot / scraper / empty UA records for deletion (unless it's the current session device)
            if (ua_meta.get('is_bot') or not ua.strip() or dev.name.startswith('Computer (Unknown OS')) and dev.device_id != current_token:
                deleted_ids.append(dev.id)
                continue

            # 2. Group by (IP, OS, Browser / Brand)
            brand_group = dev.brand_model or ua_meta.get('brand_model') or 'Device'
            os_group = dev.os_info or ua_meta.get('os_info') or 'OS'
            browser_group = dev.browser_info or ua_meta.get('browser_info') or 'Browser'
            key = (dev.last_ip or '127.0.0.1', brand_group, os_group, browser_group)

            if dev.device_id == current_token:
                if key in seen_keys:
                    prev_id = seen_keys[key]
                    if prev_id != dev.id and prev_id not in deleted_ids:
                        deleted_ids.append(prev_id)
                seen_keys[key] = dev.id
            elif key not in seen_keys:
                seen_keys[key] = dev.id
            else:
                deleted_ids.append(dev.id)

        if deleted_ids:
            AuthorizedDevice.objects.filter(id__in=deleted_ids).delete()

        return JsonResponse({
            'status': 'success',
            'deleted_count': len(deleted_ids),
            'message': f'Cleaned {len(deleted_ids)} duplicate/stale device records successfully.'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def device_delete_api(request, device_pk):
    try:
        device = AuthorizedDevice.objects.get(id=device_pk)
        device_name = device.name or device.device_id
        device.delete()

        return JsonResponse({
            'status': 'success',
            'message': f'Device "{device_name}" deleted successfully.'
        })
    except AuthorizedDevice.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'Device not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

@require_POST
def device_master_key_unlock_api(request):
    """
    Instantly authorizes a new device if the valid Master Admin Recovery Key is provided.
    """
    try:
        import json
        data = json.loads(request.body)
        device_id = data.get('device_id', '').strip()
        master_key = data.get('master_key', '').strip()
        device_name = data.get('device_name', '').strip()

        if not device_id or not master_key:
            return JsonResponse({'status': 'error', 'error': 'Device ID and Master Recovery Key are required.'}, status=400)

        from apps.authentication.models import AdminRecoveryConfig, AuthorizedDevice, SystemAuditLog
        recovery_config = AdminRecoveryConfig.get_config()

        is_locked, remaining_mins = recovery_config.is_rate_limited()
        if is_locked:
            return JsonResponse({
                'status': 'error',
                'error': f'Rate limit exceeded. Unlock is locked for {remaining_mins} more minute(s).'
            }, status=429)

        if not recovery_config.check_key(master_key):
            recovery_config.record_failed_attempt()
            SystemAuditLog.objects.create(
                user=request.user if request.user.is_authenticated else None,
                event_type='AUTH_FAILED',
                module_name='AUTHENTICATION',
                object_repr=f"Invalid Master Recovery Key entered for Device Unlock ({device_id}) (Attempt {recovery_config.failed_attempts}/3)",
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent_summary=request.META.get('HTTP_USER_AGENT', '')[:250]
            )
            return JsonResponse({'status': 'error', 'error': 'Invalid Master Recovery Key.'}, status=403)

        device_obj, _ = AuthorizedDevice.objects.get_or_create(device_id=device_id)
        device_obj.is_approved = True
        device_obj.status = 'APPROVED'
        if device_name:
            device_obj.name = device_name
        if request.user.is_authenticated:
            device_obj.approved_by = request.user
        device_obj.approved_at = timezone.now()
        device_obj.save()

        recovery_config.record_successful_reset()

        SystemAuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            event_type='UPDATE',
            module_name='Authorized Device',
            object_repr=f"Device {device_obj.name or device_id} instantly authorized via Master Recovery Key",
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent_summary=request.META.get('HTTP_USER_AGENT', '')[:250]
        )

        return JsonResponse({
            'status': 'success',
            'message': 'Device authorized successfully!'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_or_superuser)
def audit_logs_api(request):
    try:
        user_id = request.GET.get('user_id')
        event_type = request.GET.get('event_type')
        module = request.GET.get('module')
        search = request.GET.get('search', '').strip().lower()
        quick_range = request.GET.get('quick_range')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        month = request.GET.get('month')

        qs = SystemAuditLog.objects.all().select_related('user', 'device').order_by('-timestamp')

        now = timezone.now()
        if quick_range == 'TODAY':
            qs = qs.filter(timestamp__date=now.date())
        elif quick_range == 'YESTERDAY':
            yesterday = (now - datetime.timedelta(days=1)).date()
            qs = qs.filter(timestamp__date=yesterday)
        elif quick_range == 'THIS_WEEK':
            start_week = (now - datetime.timedelta(days=now.weekday())).date()
            qs = qs.filter(timestamp__date__gte=start_week, timestamp__date__lte=now.date())
        elif quick_range == 'THIS_MONTH':
            qs = qs.filter(timestamp__year=now.year, timestamp__month=now.month)
        elif quick_range == 'LAST_MONTH':
            first_this_month = now.date().replace(day=1)
            last_day_prev_month = first_this_month - datetime.timedelta(days=1)
            qs = qs.filter(timestamp__year=last_day_prev_month.year, timestamp__month=last_day_prev_month.month)

        if month:
            try:
                yr, mo = month.split('-')
                qs = qs.filter(timestamp__year=int(yr), timestamp__month=int(mo))
            except (ValueError, TypeError):
                pass

        if start_date:
            try:
                qs = qs.filter(timestamp__date__gte=datetime.date.fromisoformat(start_date))
            except ValueError:
                pass

        if end_date:
            try:
                qs = qs.filter(timestamp__date__lte=datetime.date.fromisoformat(end_date))
            except ValueError:
                pass

        if user_id:
            qs = qs.filter(user_id=int(user_id))
        if event_type:
            if event_type == 'BLOCKED_ALL':
                qs = qs.filter(event_type__in=['SECURITY_BLOCKED', 'SECURITY_REJECTED', 'AUTH_FAILED'])
            else:
                qs = qs.filter(event_type=event_type)
        if module:
            qs = qs.filter(module_name__icontains=module)
        if search:
            qs = qs.filter(
                Q(object_repr__icontains=search) | 
                Q(request_path__icontains=search) | 
                Q(ip_address__icontains=search) |
                Q(user__username__icontains=search) |
                Q(module_name__icontains=search)
            )

        logs_data = []
        for log in qs[:150]:
            logs_data.append({
                'id': log.id,
                'timestamp': log.timestamp.strftime('%d %b %Y, %H:%M:%S'),
                'username': log.user.username if log.user else 'Anonymous/System',
                'device_name': log.device.name if log.device else 'Direct/Unknown',
                'ip_address': log.ip_address or '127.0.0.1',
                'network_scope': log.get_network_scope_display(),
                'event_type': log.event_type,
                'event_display': log.get_event_type_display(),
                'module_name': log.module_name,
                'object_repr': log.object_repr or '',
                'request_path': log.request_path or '',
                'changes_json': log.changes_json
            })

        return JsonResponse({'status': 'success', 'logs': logs_data, 'total_count': qs.count()})
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def clear_audit_alerts_api(request):
    try:
        from apps.authentication.models import AdminRecoveryConfig
        cfg = AdminRecoveryConfig.get_config()
        cfg.last_security_alerts_cleared_at = timezone.now()
        cfg.save(update_fields=['last_security_alerts_cleared_at'])
        return JsonResponse({
            'status': 'success',
            'message': 'Security alerts acknowledged and alert badge cleared successfully.'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_or_superuser)
def live_activity_stream_api(request):
    try:
        activities = UserLiveActivity.objects.all().select_related('user', 'device').order_by('-last_heartbeat')[:20]
        stream_data = []
        for act in activities:
            stream_data.append({
                'id': act.id,
                'username': act.user.username,
                'role_display': act.user.get_role_display(),
                'device_name': act.device.name if act.device else 'Desktop Browser',
                'device_icon': act.device.get_device_icon() if act.device else '💻',
                'current_page': act.current_page,
                'current_path': act.current_path,
                'ip_address': act.ip_address or '127.0.0.1',
                'network_scope': '🏢 Factory Wi-Fi' if act.network_scope == 'FACTORY_LOCAL' else '🌐 Remote Network',
                'last_heartbeat': act.last_heartbeat.strftime('%H:%M:%S'),
                'is_active_now': act.is_active_now
            })
        return JsonResponse({'status': 'success', 'activities': stream_data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


@csrf_exempt
def heartbeat_api(request):
    if request.user.is_authenticated:
        try:
            device_token = request.COOKIES.get('device_token')
            device_obj = AuthorizedDevice.objects.filter(device_id=device_token).first() if device_token else None
            client_ip = get_client_ip(request)
            page_path = request.GET.get('page_path', '').strip() or request.path

            page_name = 'Dashboard'
            if '/casting' in page_path or '/casting-stock' in page_path: page_name = 'Casting Department'
            elif '/machin' in page_path or '/issue-machining' in page_path: page_name = 'Machining Department'
            elif '/polish' in page_path or '/polished-stock' in page_path: page_name = 'Polishing Department'
            elif '/packag' in page_path or '/ready-stock' in page_path or '/assembly' in page_path: page_name = 'Packaging & Stock'
            elif '/purchases' in page_path: page_name = 'Purchase Orders'
            elif '/orders' in page_path: page_name = 'Sales Orders'
            elif '/dispatch' in page_path: page_name = 'Dispatch & Sales'
            elif '/master-data' in page_path: page_name = 'Master Data Hub'
            elif '/ledger' in page_path or '/worker' in page_path: page_name = 'Labor & HR Ledger'
            elif '/attendance' in page_path: page_name = 'Attendance Register'
            elif '/sql-explorer' in page_path: page_name = 'SQL Explorer & Data Flow'
            elif '/users' in page_path: page_name = 'User Control & Permissions'

            from apps.authentication.utils import classify_network_scope
            net_scope = classify_network_scope(client_ip)
            UserLiveActivity.objects.update_or_create(
                user=request.user,
                defaults={
                    'device': device_obj,
                    'current_page': page_name,
                    'current_path': page_path,
                    'ip_address': client_ip,
                    'network_scope': net_scope
                }
            )
            if device_obj and device_obj.pk:
                device_obj.last_used_at = timezone.now()
                device_obj.save(update_fields=['last_used_at'])

            return JsonResponse({'status': 'success', 'page': page_name})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'anonymous'})


@csrf_exempt
@require_POST
def device_update_hardware_api(request):
    try:
        data = json.loads(request.body)
        exact_model = data.get('exact_model', '').strip()

        device = getattr(request, 'device', None)
        if not device:
            device_token = request.COOKIES.get('device_token')
            if device_token:
                device = AuthorizedDevice.objects.filter(device_id=device_token).first()

        if device and exact_model:
            device.brand_model = exact_model
            device.save(update_fields=['brand_model'])
            return JsonResponse({'status': 'success', 'model': exact_model})
        return JsonResponse({'status': 'ignored'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def device_quick_trust_api(request):
    """
    Quick-trust endpoint for local development or admin authorization.
    """
    try:
        from apps.authentication.middleware import get_client_ip, is_local_factory_ip
        from django.conf import settings
        client_ip = get_client_ip(request)
        is_dev = getattr(settings, 'DEBUG', False) or is_local_factory_ip(client_ip) or (request.user.is_authenticated and (request.user.is_superuser or getattr(request.user, 'role', '') == 'ADMIN'))
        
        if not is_dev:
            return JsonResponse({'status': 'error', 'error': 'Quick Trust is only permitted on local/dev network or by Admin.'}, status=403)

        device_token = request.COOKIES.get('device_token')
        if not device_token and request.body:
            try:
                data = json.loads(request.body)
                device_token = data.get('device_id')
            except Exception:
                pass

        if not device_token:
            return JsonResponse({'status': 'error', 'error': 'No device token found.'}, status=400)

        device = AuthorizedDevice.objects.filter(device_id=device_token).first()
        if not device:
            return JsonResponse({'status': 'error', 'error': 'Device record not found.'}, status=404)

        device.is_approved = True
        device.status = 'APPROVED'
        device.rejection_reason = None
        if request.user.is_authenticated:
            device.approved_by = request.user
        device.approved_at = timezone.now()
        device.save()

        return JsonResponse({
            'status': 'success',
            'message': f'Device "{device.name or device.device_id}" trusted and approved successfully.'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def device_set_security_mode_api(request):
    try:
        data = json.loads(request.body)
        new_mode = data.get('mode', '').strip()
        from apps.master_data.models import MaintenanceSettings
        valid_modes = [choice[0] for choice in MaintenanceSettings.SECURITY_MODE_CHOICES]
        if new_mode not in valid_modes:
            return JsonResponse({'status': 'error', 'error': f'Invalid security mode "{new_mode}".'}, status=400)

        m_settings, _ = MaintenanceSettings.objects.get_or_create(id=1)
        m_settings.device_security_mode = new_mode
        m_settings.save()

        return JsonResponse({
            'status': 'success',
            'mode': new_mode,
            'message': f'Device Security Mode updated to "{new_mode}".'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


@require_POST
def admin_emergency_reset_api(request):
    """
    Emergency Password Reset for Admin accounts using the Master Recovery Key.
    Rate-limited: 3 failed attempts triggers 30 min lockout.
    """
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        recovery_key = data.get('recovery_key', '').strip()
        new_password = data.get('new_password', '').strip()
        confirm_password = data.get('confirm_password', '').strip()

        if not username or not recovery_key or not new_password:
            return JsonResponse({'status': 'error', 'error': 'All fields are required.'}, status=400)

        if len(new_password) < 6:
            return JsonResponse({'status': 'error', 'error': 'New password must be at least 6 characters long.'}, status=400)

        if confirm_password and new_password != confirm_password:
            return JsonResponse({'status': 'error', 'error': 'New password and confirmation do not match.'}, status=400)

        from apps.authentication.models import AdminRecoveryConfig, CustomUser, SystemAuditLog
        recovery_config = AdminRecoveryConfig.get_config()

        is_locked, remaining_mins = recovery_config.is_rate_limited()
        if is_locked:
            return JsonResponse({
                'status': 'error', 
                'error': f'Rate limit exceeded. Emergency reset is locked for {remaining_mins} more minute(s).'
            }, status=429)

        # Strictly verify user exists and is an Admin / Superuser
        user = CustomUser.objects.filter(username=username, is_active=True).first()
        if not user or not (user.is_superuser or getattr(user, 'role', '') == 'ADMIN'):
            recovery_config.record_failed_attempt()
            SystemAuditLog.objects.create(
                user=None,
                event_type='AUTH_FAILED',
                module_name='AUTHENTICATION',
                object_repr=f"Failed admin emergency recovery attempt for unknown/non-admin username: '{username}'",
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent_summary=request.META.get('HTTP_USER_AGENT', '')[:250]
            )
            return JsonResponse({'status': 'error', 'error': 'Emergency recovery is only available for Super Admins.'}, status=403)

        # Check recovery key
        if not recovery_config.check_key(recovery_key):
            recovery_config.record_failed_attempt()
            SystemAuditLog.objects.create(
                user=user,
                event_type='AUTH_FAILED',
                module_name='AUTHENTICATION',
                object_repr=f"Invalid Master Recovery Key entered for admin '{user.username}' (Attempt {recovery_config.failed_attempts}/3)",
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent_summary=request.META.get('HTTP_USER_AGENT', '')[:250]
            )
            attempts_left = max(0, 3 - recovery_config.failed_attempts)
            if attempts_left == 0:
                msg = "Invalid Master Recovery Key. Account recovery is now locked for 30 minutes."
            else:
                msg = f"Invalid Master Recovery Key. {attempts_left} attempt(s) remaining before 30-minute lockout."
            return JsonResponse({'status': 'error', 'error': msg}, status=400)

        # Reset password
        user.set_password(new_password)
        user.save()
        recovery_config.record_successful_reset()

        # Log audit
        SystemAuditLog.objects.create(
            user=user,
            event_type='UPDATE',
            module_name='AUTHENTICATION',
            object_repr=f"Admin password successfully reset via Master Recovery Key for '{user.username}'",
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent_summary=request.META.get('HTTP_USER_AGENT', '')[:250]
        )

        from django.contrib.auth import login
        login(request, user)

        return JsonResponse({
            'status': 'success',
            'message': f"Password for {user.username} has been reset successfully. Logging in...",
            'redirect_url': '/select-company/'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_or_superuser)
@require_POST
def admin_update_recovery_key_api(request):
    """
    Update or Rotate the Master Recovery Key. Requires current admin password verification.
    """
    try:
        data = json.loads(request.body)
        current_password = data.get('current_password', '').strip()
        new_recovery_key = (data.get('new_recovery_key') or data.get('new_master_key', '')).strip()
        key_hint = data.get('key_hint', '').strip()

        if not current_password or not new_recovery_key:
            return JsonResponse({'status': 'error', 'error': 'Current password and new recovery key are required.'}, status=400)

        if not request.user.check_password(current_password):
            return JsonResponse({'status': 'error', 'error': 'Current admin password verification failed.'}, status=403)

        if len(new_recovery_key) < 6:
            return JsonResponse({'status': 'error', 'error': 'Recovery key must be at least 6 characters long.'}, status=400)

        from apps.authentication.models import AdminRecoveryConfig, SystemAuditLog
        cfg = AdminRecoveryConfig.get_config()
        cfg.set_key(new_recovery_key, hint=key_hint, user=request.user)

        SystemAuditLog.objects.create(
            user=request.user,
            event_type='UPDATE',
            module_name='SECURITY',
            object_repr=f"Master Recovery Key updated/rotated by {request.user.username}",
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent_summary=request.META.get('HTTP_USER_AGENT', '')[:250]
        )

        return JsonResponse({
            'status': 'success',
            'message': 'Master Recovery Key updated successfully.',
            'key_hint': cfg.key_hint,
            'updated_at': cfg.updated_at.strftime('%d %b %Y, %I:%M %p')
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)



