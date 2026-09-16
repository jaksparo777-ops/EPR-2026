from django.db.models.signals import post_save, post_delete
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
import json
import threading
import time

from apps.authentication.utils import log_system_audit_event

_thread_locals = threading.local()

def _get_current_request():
    return getattr(_thread_locals, 'request', None)

def set_current_request(request):
    _thread_locals.request = request

def clear_current_request():
    _thread_locals.request = None


def serialize_model_instance(instance):
    """
    Serializes a Django model instance into a JSON-friendly dict.
    """
    try:
        data = {}
        for field in instance._meta.fields:
            val = getattr(instance, field.name, None)
            if val is not None:
                if hasattr(val, 'isoformat'):
                    data[field.name] = val.isoformat()
                elif hasattr(val, 'pk'):
                    data[field.name] = str(val)
                else:
                    try:
                        json.dumps(val)
                        data[field.name] = val
                    except TypeError:
                        data[field.name] = str(val)
        return data
    except Exception:
        return {'id': getattr(instance, 'pk', None)}


def track_model_audit_event(instance, created, deleted=False):
    """
    Tracks CREATE, UPDATE, or DELETE events for key ERP models.
    """
    try:
        req = _get_current_request()
        user = getattr(req, 'user', None) if req else None
        if user and not getattr(user, 'is_authenticated', False):
            user = None
            
        device = getattr(req, 'device', None) if req else None
        ip_addr = getattr(req, 'META', {}).get('REMOTE_ADDR', None) if req else None
        request_path = getattr(req, 'path', None) if req else None
        user_agent = getattr(req, 'META', {}).get('HTTP_USER_AGENT', None) if req else None

        model_name = instance._meta.verbose_name.title() if hasattr(instance._meta, 'verbose_name') else instance.__class__.__name__
        object_repr = str(instance)[:255]
        object_id = str(instance.pk)

        if deleted:
            event_type = 'DELETE'
            changes = {'deleted_record': serialize_model_instance(instance)}
        elif created:
            event_type = 'CREATE'
            changes = {'new_record': serialize_model_instance(instance)}
        else:
            event_type = 'UPDATE'
            changes = {'updated_record': serialize_model_instance(instance)}

        log_system_audit_event(
            user=user,
            device=device,
            ip_address=ip_addr,
            event_type=event_type,
            module_name=model_name,
            object_id=object_id,
            object_repr=object_repr,
            changes_json=changes,
            request_path=request_path,
            user_agent_summary=user_agent
        )
    except Exception as e:
        import logging
        logging.getLogger('django').error(f"Audit signal error: {e}")


def on_model_post_save(sender, instance, created, **kwargs):
    if sender.__name__ in ('SystemAuditLog', 'UserLiveActivity', 'Session', 'LogEntry', 'ContentType', 'Permission', 'AuthorizedDevice'):
        return
    track_model_audit_event(instance, created=created, deleted=False)


def on_model_post_delete(sender, instance, **kwargs):
    if sender.__name__ in ('SystemAuditLog', 'UserLiveActivity', 'Session', 'LogEntry', 'ContentType', 'Permission', 'AuthorizedDevice'):
        return
    track_model_audit_event(instance, created=False, deleted=True)


def register_audit_signals():
    """
    Dynamically connects post_save and post_delete receivers to all core ERP models.
    """
    from django.apps import apps
    for m in apps.get_models():
        if m.__name__ not in ('SystemAuditLog', 'UserLiveActivity', 'Session', 'LogEntry', 'ContentType', 'Permission'):
            post_save.connect(on_model_post_save, sender=m, weak=False)
            post_delete.connect(on_model_post_delete, sender=m, weak=False)


@receiver(user_logged_in)
def handle_user_login(sender, request, user, **kwargs):
    """
    On fresh user login:
    - Set initial last_user_activity timestamp for inactivity tracking.
    - If user has global access, role ADMIN, or multiple allowed companies:
      Clear any pre-existing active_company_id in the session so they are required
      to pick their desired workspace on the select_company screen.
    - If user has only 1 company and no global access, auto-assign their active company.
    """
    if request and hasattr(request, 'session'):
        request.session['last_user_activity'] = time.time()

    can_access_global = getattr(user, 'is_superuser', False) or getattr(user, 'role', '') == 'ADMIN' or getattr(user, 'is_global_access', False)
    allowed_count = user.get_allowed_companies().count() if hasattr(user, 'get_allowed_companies') else 0

    if can_access_global or allowed_count > 1:
        if request and hasattr(request, 'session') and 'active_company_id' in request.session:
            del request.session['active_company_id']
    elif allowed_count == 1:
        comp = user.get_allowed_companies().first()
        if comp and request and hasattr(request, 'session'):
            request.session['active_company_id'] = comp.id


@receiver(user_logged_out)
def handle_user_logout(sender, request, user, **kwargs):
    """
    On user logout:
    Clear active_company_id and last_user_activity from session to ensure clean slate for subsequent logins.
    """
    if request and hasattr(request, 'session'):
        for key in ('active_company_id', 'last_user_activity'):
            if key in request.session:
                try:
                    del request.session[key]
                except KeyError:
                    pass

