from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.profile_view, name='profile'),
    path('update/', views.update_profile, name='update_profile'),
    path('withdraw/', views.withdraw_wallet, name='withdraw'),
    path('spin/', views.spin_page, name='spin'),
    path('spin/go/', views.spin_wheel, name='spin_wheel'),
    path('spin/<int:spin_id>/claim/', views.claim_prize, name='claim_prize'),
]
