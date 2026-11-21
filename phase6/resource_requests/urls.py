from django.urls import path

from . import views

urlpatterns = [
    path("mine/", views.my_requests, name="my_requests"),
    path("tasks/", views.tasks, name="tasks"),
    path("new/<int:asset_pk>/", views.request_create, name="request_create"),
    path("<int:pk>/", views.request_detail, name="request_detail"),
    path("<int:pk>/release/", views.release, name="request_release"),
    path("<int:pk>/decline/", views.decline, name="request_decline"),
    path("<int:pk>/approve/", views.approve, name="request_approve"),
    path("<int:pk>/reject/", views.reject, name="request_reject"),
    path("<int:pk>/hand-over/", views.hand_over, name="request_hand_over"),
    path("<int:pk>/confirm/", views.confirm_receipt, name="request_confirm"),
    path("<int:pk>/cancel/", views.cancel, name="request_cancel"),
]
