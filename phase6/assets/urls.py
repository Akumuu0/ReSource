from django.urls import path

from . import views

urlpatterns = [
    path("", views.asset_list, name="asset_list"),
    path("mine/", views.my_assets, name="my_assets"),
    path("new/", views.asset_form, name="asset_create"),
    path("<int:pk>/", views.asset_detail, name="asset_detail"),
    path("<int:pk>/edit/", views.asset_form, name="asset_edit"),
    path("<int:pk>/publish/", views.publish, name="asset_publish"),
    path("<int:pk>/withdraw/", views.withdraw, name="asset_withdraw"),
]
