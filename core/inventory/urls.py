from django.urls import path

from inventory.views import (

    dashboard,

    casting_entry,

    master_data,

    casting_stock,

    machining_stock,

    machining_entry,

    polishing_entry,

    packaging_view,

    issue_machining,

    delete_item,

    edit_item,

    dispatch_view,

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
        'machining/',
        machining_entry,
        name='machining_entry'
    ),

    path(
        'polishing/',
        polishing_entry,
        name='polishing_entry'
    ),

    path(
        'packaging/',
        packaging_view,
        name='packaging'
    ),

    path(
        'master-data/',
        master_data,
        name='master_data'
    ),

    path(
        'casting-stock/',
        casting_stock,
        name='casting_stock'
    ),

    path(
        'machining-stock/',
        machining_stock,
        name='machining_stock'
    ),

    path(
        'issue-machining/',
        issue_machining,
        name='issue_machining'
    ),

    path(
        'delete-item/<int:item_id>/',
        delete_item,
        name='delete_item'
    ),

    path(
        'edit-item/<int:item_id>/',
        edit_item,
        name='edit_item'
    ),

    path(
        'dispatch/',
        dispatch_view,
        name='dispatch'
    ),
    
]