from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from apps.master_data.models import LegalEntity
from apps.authentication.models import CustomUser, AuthorizedDevice, SystemAuditLog, UserLiveActivity

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
        if company_id == 'global' and can_access_global:
            request.session['active_company_id'] = 'global'
            return redirect('dashboard')

        if company_id and str(company_id).isdigit():
            cid = int(company_id)
            if user.can_access_company(cid):
                request.session['active_company_id'] = cid
                return redirect('dashboard')

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
    
    current_device_id = getattr(request, 'device', None).device_id if hasattr(request, 'device') and request.device else request.COOKIES.get('device_token', '')
    
    audit_logs_qs = SystemAuditLog.objects.all().select_related('user', 'device').order_by('-timestamp')
    live_activities_list = UserLiveActivity.objects.all().select_related('user', 'device').order_by('-last_heartbeat')[:20]
    
    total_audit_logs = audit_logs_qs.count()
    security_blocked_count = audit_logs_qs.filter(event_type__in=['SECURITY_BLOCKED', 'SECURITY_REJECTED', 'AUTH_FAILED']).count()
    audit_logs_list = audit_logs_qs[:100]

    from apps.master_data.models import MaintenanceSettings
    m_settings, _ = MaintenanceSettings.objects.get_or_create(id=1)

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
        'current_device_id': current_device_id,
        'audit_logs_list': audit_logs_list,
        'live_activities_list': live_activities_list,
        'total_audit_logs': total_audit_logs,
        'security_blocked_count': security_blocked_count,
        'now_time': timezone.now(),
        'device_security_mode': m_settings.device_security_mode,
        'security_mode_choices': MaintenanceSettings.SECURITY_MODE_CHOICES,
        'default_permissions_json': json.dumps(get_default_permission_tree())
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

@login_required
@user_passes_test(is_admin_or_superuser)
def audit_logs_api(request):
    try:
        user_id = request.GET.get('user_id')
        event_type = request.GET.get('event_type')
        module = request.GET.get('module')
        search = request.GET.get('search', '').strip().lower()

        qs = SystemAuditLog.objects.all().select_related('user', 'device').order_by('-timestamp')

        if user_id:
            qs = qs.filter(user_id=int(user_id))
        if event_type:
            qs = qs.filter(event_type=event_type)
        if module:
            qs = qs.filter(module_name__icontains=module)
        if search:
            qs = qs.filter(
                Q(object_repr__icontains=search) | 
                Q(request_path__icontains=search) | 
                Q(ip_address__icontains=search) |
                Q(user__username__icontains=search)
            )

        logs_data = []
        for log in qs[:100]:
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


