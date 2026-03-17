from django.contrib import admin

from .models import ChatMessage, Repository


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "total_files", "total_chunks", "uploaded_at")
    list_filter = ("status", "uploaded_at")
    search_fields = ("name", "path")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "repository", "created_at")
    search_fields = ("question", "answer")
