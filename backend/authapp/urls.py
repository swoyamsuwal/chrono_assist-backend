from django.urls import path
from . import views

urlpatterns = [
    path('csrf/', views.get_csrf, name='get_csrf'),
    path('register/', views.register_api, name='register_api'),
    path('login/', views.login_api, name='login_api'),
    path('verify-otp/', views.verify_otp_api, name='verify_otp_api'),
]
