from django.urls import path

from .views import (
    ask_question,
    ask_question_legacy,
    login_view,
    logout_view,
    repositories,
    repository_files,
    signup_view,
    upload_repo,
    workspace,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("signup/", signup_view, name="signup"),
    path("logout/", logout_view, name="logout"),
    path("", workspace, name="workspace"),
    path("ask/", ask_question_legacy, name="ask_question_legacy"),
    path("api/repositories/", repositories, name="repositories"),
    path("api/repositories/<int:repository_id>/files/", repository_files, name="repository_files"),
    path("api/upload/", upload_repo, name="upload_repo"),
    path("api/ask/", ask_question, name="ask_question"),
]
