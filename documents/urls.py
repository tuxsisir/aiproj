from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.document_library, name="library"),
    path("upload/", views.document_upload, name="upload"),
    path("ask/", views.ask_documents, name="ask"),
    path("questions/<uuid:pk>/", views.question_detail, name="question"),
    path("<uuid:pk>/", views.document_detail, name="detail"),
    path("<uuid:pk>/summary/", views.document_summary, name="summary"),
    path("<uuid:pk>/file/", views.document_file, name="file"),
    path("<uuid:pk>/retry/", views.document_retry_summary, name="retry"),
    path("<uuid:pk>/delete/", views.document_delete, name="delete"),
]
