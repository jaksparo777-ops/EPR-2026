from django.apps import AppConfig

class MonitoringConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.monitoring'
    verbose_name = 'Operator Security & Monitoring'

    def ready(self):
        import apps.monitoring.signals
