from django.urls import path

from . import views

app_name = 'marketing'

urlpatterns = [
    path('', views.campaign_list, name='list'),
    path('share/<int:campaign_id>/start/', views.create_share, name='create_share'),
    path('r/<str:code>/', views.redirect_view, name='redirect'),
    path('earnings/', views.my_earnings, name='earnings'),
    path('share/<int:share_id>/proof/', views.upload_proof, name='upload_proof'),
    path('withdraw/', views.request_withdrawal, name='withdraw'),
    path('withdrawals/', views.withdrawal_history, name='withdrawals'),
    path('internal/process-proofs/', views.process_proofs_endpoint, name='process_proofs'),
]
