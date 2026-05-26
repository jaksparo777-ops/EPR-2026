from django.urls import path
from apps.logistics.views import packaging_view, dispatch_view

urlpatterns = [
    path('packaging/', packaging_view, name='packaging'),
    path('dispatch/', dispatch_view, name='dispatch'),
]
