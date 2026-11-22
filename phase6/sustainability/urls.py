from django.urls import path

from . import views

urlpatterns = [
    path("sustainability/", views.dashboard, name="dashboard"),
]
