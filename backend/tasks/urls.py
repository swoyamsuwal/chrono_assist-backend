from django.urls import path
from . import views

urlpatterns = [
    path("tasks/", views.create_task),
    path("tasks/board/", views.board),
    path("tasks/<int:pk>/", views.retrieve_task),
    path("tasks/<int:pk>/update/", views.update_task),
    path("tasks/<int:pk>/delete/", views.delete_task),
]
