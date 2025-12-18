from django.urls import path
from .views import GenerateEmailView, SendEmailView

urlpatterns = [
    path("generate/", GenerateEmailView.as_view(), name="mail-generate"),
    path("send/", SendEmailView.as_view(), name="mail-send"),
]
