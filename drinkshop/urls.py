from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('profile/', include('accounts.urls', namespace='accounts')),
    path('careers/', include('careers.urls', namespace='careers')),
    path('sell/', include('vendors.urls', namespace='vendors')),
    path('', include('store.urls', namespace='store')),
    path('orders/', include('orders.urls', namespace='orders')),
    path('payments/', include('payments.urls', namespace='payments')),
    path('marketing/', include('marketing.urls', namespace='marketing')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
