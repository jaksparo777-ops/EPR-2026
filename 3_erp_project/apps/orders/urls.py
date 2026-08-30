from django.urls import path
from .views import orders_board, order_details_api, dispatch_order, create_order_view, delete_order

urlpatterns = [
    path('', orders_board, name='orders_board'),
    path('create/', create_order_view, name='create_order'),
    path('api/<int:order_id>/', order_details_api, name='order_details_api'),
    path('<int:order_id>/dispatch/', dispatch_order, name='dispatch_order'),
    path('<int:order_id>/delete/', delete_order, name='delete_order'),
]
