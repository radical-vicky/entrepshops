from django.urls import path

from . import views

app_name = 'vendors'

urlpatterns = [
    path('', views.become_vendor, name='become_vendor'),
    path('subscribe/', views.subscribe, name='subscribe'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('products/add/', views.product_form, name='product_add'),
    path('products/<int:product_id>/edit/', views.product_form, name='product_edit'),
    path('products/<int:product_id>/delete/', views.product_delete, name='product_delete'),
]
