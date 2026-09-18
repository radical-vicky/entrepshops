from django.urls import path

from . import views

app_name = 'careers'

urlpatterns = [
    path('', views.job_list, name='list'),
    path('<slug:slug>/', views.job_detail, name='detail'),
    path('<slug:slug>/apply/', views.apply, name='apply'),
]
