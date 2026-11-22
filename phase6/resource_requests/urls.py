from django.urls import path

from . import views

urlpatterns = [
    path("mine/", views.my_requests, name="my_requests"),
    path("tasks/", views.tasks, name="tasks"),
    path("new/<int:asset_pk>/", views.request_create, name="request_create"),
    path("need/", views.need_create, name="need_create"),
    path("<int:pk>/matches/", views.matches, name="request_matches"),
    path("<int:pk>/matches/choose/<int:rec_pk>/", views.choose_match, name="request_choose_match"),
    path("<int:pk>/matches/reject/", views.reject_matches, name="request_reject_matches"),
    path("<int:pk>/", views.request_detail, name="request_detail"),
    path("<int:pk>/release/", views.release, name="request_release"),
    path("<int:pk>/decline/", views.decline, name="request_decline"),
    path("<int:pk>/approve/", views.approve, name="request_approve"),
    path("<int:pk>/reject/", views.reject, name="request_reject"),
    path("<int:pk>/hand-over/", views.hand_over, name="request_hand_over"),
    path("<int:pk>/confirm/", views.confirm_receipt, name="request_confirm"),
    path("<int:pk>/cancel/", views.cancel, name="request_cancel"),
]
