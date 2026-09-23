from django.db.models import Q
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination

from store.models import Category, Department, Product

from .serializers import (
    CategorySerializer, DepartmentSerializer,
    ProductDetailSerializer, ProductListSerializer,
)


class ProductPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = 'page_size'
    max_page_size = 100


class ProductListView(generics.ListAPIView):
    """GET /api/v1/products/ — the grid endpoint.

    Query params:
      ?department=<slug>
      ?category=<slug>
      ?q=<search>
      ?page=<n>
      ?page_size=<n>
    """
    serializer_class = ProductListSerializer
    pagination_class = ProductPagination

    def get_queryset(self):
        qs = Product.objects.visible().select_related(
            'category', 'department'
        ).prefetch_related('images', 'variants')

        department = self.request.query_params.get('department')
        category = self.request.query_params.get('category')
        q = self.request.query_params.get('q')

        if department:
            qs = qs.filter(department__slug=department)
        if category:
            qs = qs.filter(category__slug=category)
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(description__icontains=q)
            )
        return qs


class ProductDetailView(generics.RetrieveAPIView):
    """GET /api/v1/products/<slug>/"""
    serializer_class = ProductDetailSerializer
    lookup_field = 'slug'
    queryset = Product.objects.visible().select_related(
        'category', 'department'
    ).prefetch_related('variants', 'images', 'offers')


class DepartmentListView(generics.ListAPIView):
    """GET /api/v1/departments/"""
    serializer_class = DepartmentSerializer
    queryset = Department.objects.filter(is_active=True)
    pagination_class = None


class CategoryListView(generics.ListAPIView):
    """GET /api/v1/categories/ — filterable by ?department=<slug>"""
    serializer_class = CategorySerializer
    pagination_class = None

    def get_queryset(self):
        qs = Category.objects.select_related('department')
        department = self.request.query_params.get('department')
        if department:
            qs = qs.filter(department__slug=department)
        return qs
