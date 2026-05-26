from django.urls import path
from apps.production.views import (
    casting_entry,
    machining_entry,
    polishing_entry,
    assembly_view,
    casting_stock,
    machining_stock,
    polishing_stock,
    ready_stock,
    issue_machining,
)

urlpatterns = [
    path('casting/', casting_entry, name='casting_entry'),
    path('machining/', machining_entry, name='machining_entry'),
    path('polishing/', polishing_entry, name='polishing_entry'),
    path('assembly/', assembly_view, name='assembly'),
    path('casting-stock/', casting_stock, name='casting_stock'),
    path('machining-stock/', machining_stock, name='machining_stock'),
    path('polishing-stock/', polishing_stock, name='polishing_stock'),
    path('ready-stock/', ready_stock, name='ready_stock'),
    path('issue-machining/', issue_machining, name='issue_machining'),
]
