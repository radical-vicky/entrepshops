from django.urls import path

from . import views

app_name = 'orders'

urlpatterns = [
    path('checkout/', views.checkout, name='checkout'),
    path('waiting/<int:order_id>/', views.payment_waiting, name='payment_waiting'),
    path('waiting/<int:order_id>/retry/', views.retry_payment, name='retry_payment'),
    path('history/', views.order_history, name='order_history'),
    path('<int:order_id>/', views.order_detail, name='order_detail'),
    path('<int:order_id>/receipt/', views.download_receipt, name='download_receipt'),
    path('items/<int:item_id>/review/', views.submit_review, name='submit_review'),
    path('<int:order_id>/tip/', views.send_tip, name='send_tip'),

    path('rider/', views.rider_dashboard, name='rider_dashboard'),
    path('rider/<int:order_id>/out-for-delivery/', views.rider_mark_out_for_delivery, name='rider_mark_out_for_delivery'),
    path('rider/<int:order_id>/delivered/', views.rider_mark_delivered, name='rider_mark_delivered'),
]
