from __future__ import annotations

import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from core.embeddings import get_embedding_backend
from core.forms import LoginForm, SignUpForm
from core.models import ChatMessage, Repository
from core.services.answer_service import build_answer, format_sources, retrieve_context
from core.services.repository_service import (
    index_repository,
    reset_repository_folder,
    save_uploaded_repository,
)
from core.vector_store import list_repository_files


def _repository_payload(repository: Repository, include_files: bool = False) -> dict:
    payload = {
        "id": repository.id,
        "name": repository.name,
        "status": repository.status,
        "uploaded_at": repository.uploaded_at.isoformat(),
        "total_files": repository.total_files,
        "total_chunks": repository.total_chunks,
        "error_message": repository.error_message,
    }
    if include_files and repository.status == Repository.Status.READY:
        try:
            payload["files"] = list_repository_files(repository.id)
        except Exception:
            payload["files"] = []
    return payload


@require_http_methods(["GET", "POST"])
def signup_view(request):
    if request.user.is_authenticated:
        return redirect("workspace")

    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("login")
    return render(request, "signup.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("workspace")

    form = LoginForm(request.POST or None)
    error_message = ""
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        password = form.cleaned_data["password"]
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return redirect(request.POST.get("next") or "workspace")
        error_message = "Invalid gmail or password."
    return render(
        request,
        "login.html",
        {
            "form": form,
            "error_message": error_message,
            "next": request.GET.get("next", ""),
        },
    )


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect("login")


@ensure_csrf_cookie
@login_required(login_url="login")
def workspace(request):
    return render(request, "upload.html")


@login_required(login_url="login")
@require_http_methods(["GET"])
def repositories(request):
    queryset = Repository.objects.filter(user=request.user).order_by("-uploaded_at")
    data = [_repository_payload(repo) for repo in queryset]
    return JsonResponse({"repositories": data})


@login_required(login_url="login")
@require_http_methods(["GET"])
def repository_files(request, repository_id: int):
    repository = get_object_or_404(Repository, pk=repository_id, user=request.user)
    if repository.status != Repository.Status.READY:
        return JsonResponse(
            {
                "status": "error",
                "message": "Repository is not indexed yet",
            },
            status=400,
        )
    files = list_repository_files(repository.id)
    return JsonResponse(
        {
            "status": "success",
            "repository": _repository_payload(repository),
            "files": files,
        }
    )


@login_required(login_url="login")
@require_http_methods(["POST"])
def upload_repo(request):
    uploaded = request.FILES.get("repo")
    if not uploaded:
        return JsonResponse(
            {"status": "error", "message": "No repository zip uploaded"},
            status=400,
        )
    if not uploaded.name.lower().endswith(".zip"):
        return JsonResponse(
            {"status": "error", "message": "Only .zip repositories are supported"},
            status=400,
        )

    repository = Repository.objects.create(
        name=uploaded.name,
        path="",
        status=Repository.Status.PROCESSING,
        user=request.user,
    )

    repo_folder = None
    try:
        repo_folder, extracted_dir = save_uploaded_repository(uploaded)
        repository.path = str(extracted_dir)
        repository.save(update_fields=["path"])

        result = index_repository(repository.id, str(extracted_dir))
        repository.status = Repository.Status.READY
        repository.index_path = result["index_path"]
        repository.total_files = result["total_files"]
        repository.total_chunks = result["total_chunks"]
        repository.error_message = ""
        repository.save(
            update_fields=[
                "status",
                "index_path",
                "total_files",
                "total_chunks",
                "error_message",
            ]
        )

        return JsonResponse(
            {
                "status": "success",
                "repository": _repository_payload(repository),
                "indexed_files": result["indexed_files"][:300],
                "embedding_backend": get_embedding_backend(),
            }
        )
    except Exception as exc:
        repository.status = Repository.Status.FAILED
        repository.error_message = str(exc)
        repository.save(update_fields=["status", "error_message"])
        if repo_folder is not None:
            reset_repository_folder(str(repo_folder))
        return JsonResponse(
            {
                "status": "error",
                "message": f"Indexing failed: {exc}",
            },
            status=500,
        )


@login_required(login_url="login")
@require_http_methods(["POST"])
def ask_question(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}

    question = str(payload.get("question", "")).strip()
    repository_id = payload.get("repository_id")

    if not question:
        return JsonResponse(
            {
                "status": "error",
                "message": "Ask a question about the indexed repository.",
            },
            status=400,
        )

    repository = None
    if repository_id:
        repository = get_object_or_404(Repository, pk=repository_id, user=request.user)
    else:
        repository = (
            Repository.objects.filter(user=request.user, status=Repository.Status.READY)
            .order_by("-uploaded_at")
            .first()
        )

    if not repository:
        return JsonResponse(
            {
                "status": "error",
                "message": "Upload and index a repository first.",
            },
            status=400,
        )

    if repository.status != Repository.Status.READY:
        return JsonResponse(
            {
                "status": "error",
                "message": "Selected repository is not ready yet.",
            },
            status=400,
        )

    try:
        top_k = int(payload.get("top_k", 6))
    except (TypeError, ValueError):
        top_k = 6
    top_k = max(1, min(top_k, 10))
    results = retrieve_context(repository_id=repository.id, question=question, top_k=top_k)
    answer = build_answer(question=question, results=results)
    sources = format_sources(results)

    chat_message = ChatMessage.objects.create(
        user=request.user,
        repository=repository,
        question=question,
        answer=answer,
        sources=sources,
    )

    return JsonResponse(
        {
            "status": "success",
            "message_id": chat_message.id,
            "repository": _repository_payload(repository),
            "answer": answer,
            "sources": sources,
            "embedding_backend": get_embedding_backend(),
        }
    )


@login_required(login_url="login")
@require_http_methods(["GET"])
def ask_question_legacy(request):
    question = request.GET.get("q", "").strip()
    if not question:
        return JsonResponse({"answer": "Ask something about the repository."})

    ready_repo = (
        Repository.objects.filter(user=request.user, status=Repository.Status.READY)
        .order_by("-uploaded_at")
        .first()
    )
    if not ready_repo:
        return JsonResponse({"answer": "Upload and index a repository first."})

    results = retrieve_context(repository_id=ready_repo.id, question=question, top_k=5)
    answer = build_answer(question=question, results=results)
    return JsonResponse({"answer": answer})
