from django.urls import path

from . import views

urlpatterns = [
    path("mine/", views.my_requests, name="my_requests"),
    path("tasks/", views.tasks, name="tasks"),
    path("new/<int:asset_pk>/", views.request_create, name="request_create"),
    path("<int:pk>/", views.request_detail, name="request_detail"),
    path("<int:pk>/cancel/", views.cancel, name="request_cancel"),
]
