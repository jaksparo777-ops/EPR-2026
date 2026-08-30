from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    name = 'apps.authentication'

    def ready(self):
        import apps.authentication.signals
        apps.authentication.signals.register_audit_signals()
