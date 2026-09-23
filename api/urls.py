from django.urls import path

from . import views

app_name = 'api'

urlpatterns = [
    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/<slug:slug>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('departments/', views.DepartmentListView.as_view(), name='department-list'),
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
]
