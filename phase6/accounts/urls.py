from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", auth_views.LoginView.as_view(), name="login"),  # Django's built-in login
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/read/", views.mark_all_read, name="notifications_read"),
]
