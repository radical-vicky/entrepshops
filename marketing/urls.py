from django.urls import path

from . import views

app_name = 'marketing'

urlpatterns = [
    path('', views.campaign_list, name='list'),
    path('share/<int:campaign_id>/start/', views.create_share, name='create_share'),
    path('r/<str:code>/', views.redirect_view, name='redirect'),
    path('earnings/', views.my_earnings, name='earnings'),
]