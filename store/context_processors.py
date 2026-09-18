from .cart import Cart
from .models import BackgroundImage, Department, SiteLogo


def cart(request):
    return {'cart': Cart(request)}


def site_settings(request):
    current_department = None
    dept_id = request.session.get('current_department_id')
    if dept_id:
        current_department = Department.objects.filter(id=dept_id, is_active=True).first()
    return {
        'active_background': BackgroundImage.get_active(),
        'active_logo': SiteLogo.get_active(),
        'current_department': current_department,
    }
