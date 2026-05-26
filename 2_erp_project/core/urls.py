from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Modular sub-applications global inclusion
    path('', include('apps.products.urls')),
    path('', include('apps.production.urls')),
    path('', include('apps.logistics.urls')),
    path('', include('apps.workforce.urls')),
    path('', include('apps.ledger_pay.urls')),
    path('', include('apps.monitoring.urls')),
]
