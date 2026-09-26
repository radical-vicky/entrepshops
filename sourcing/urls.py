from django.urls import path

from . import views

app_name = 'sourcing'

urlpatterns = [
    path('', views.request_list, name='request_list'),
    path('new/', views.request_create, name='request_create'),
    path('<str:reference>/', views.request_detail, name='request_detail'),
    path('<str:reference>/cancel/', views.request_cancel, name='request_cancel'),
    path('<str:reference>/pay-deposit/', views.pay_deposit, name='pay_deposit'),
]
