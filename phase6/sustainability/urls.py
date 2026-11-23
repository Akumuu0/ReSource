from django.urls import path

from . import views

urlpatterns = [
    path("sustainability/", views.dashboard, name="dashboard"),
    path("reports/", views.report_table, name="report_table"),
    path("reports/summaries/", views.summary_list, name="summary_list"),
    path("reports/summaries/new/", views.summary_create, name="summary_create"),
    path("reports/summaries/<int:pk>/", views.summary_detail, name="summary_detail"),
]
