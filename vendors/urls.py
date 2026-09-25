from django.urls import path

from . import views

app_name = 'vendors'

urlpatterns = [
    path('', views.become_vendor, name='become_vendor'),
    path('start-trial/', views.start_trial, name='start_trial'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.edit_profile, name='edit_profile'),

    path('products/', views.product_list, name='product_list'),
    path('products/new/', views.product_create, name='product_create'),
    path('products/<int:product_id>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:product_id>/delete/', views.product_delete, name='product_delete'),
]
