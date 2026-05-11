from django.urls import path

from inventory.views import (
    dashboard,
    casting_entry,
    master_data,
)

urlpatterns = [

    path(
        '',
        dashboard,
        name='dashboard'
    ),

    path(
        'casting/',
        casting_entry,
        name='casting_entry'
    ),

    path(
        'master-data/',
        master_data,
        name='master_data'
    ),

]