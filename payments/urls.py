from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('mpesa/callback/', views.mpesa_callback, name='mpesa_callback'),
    path('status/<int:order_id>/', views.payment_status, name='payment_status'),
    path('tip-status/<int:tip_id>/', views.tip_status, name='tip_status'),
    path('mpesa/b2c/result/', views.b2c_result, name='b2c_result'),
    path('mpesa/b2c/timeout/', views.b2c_timeout, name='b2c_timeout'),
]
