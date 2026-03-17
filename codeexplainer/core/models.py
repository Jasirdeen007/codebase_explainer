from django.db import models

from core.embeddings import EMBEDDING_DIMENSION
from core.fields import VectorField


class Repository(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    name = models.CharField(max_length=200)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    path = models.CharField(max_length=500)
    index_path = models.CharField(max_length=500, blank=True, default="")
    total_files = models.PositiveIntegerField(default=0)
    total_chunks = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROCESSING,
    )
    error_message = models.TextField(blank=True, default="")
    user = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        related_name="repositories",
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f"{self.name} ({self.status})"


class ChatMessage(models.Model):
    user = models.ForeignKey(
        "auth.User",
        null=True,
        blank=True,
        related_name="chat_messages",
        on_delete=models.CASCADE,
    )
    repository = models.ForeignKey(
        Repository,
        null=True,
        blank=True,
        related_name="messages",
        on_delete=models.CASCADE,
    )
    question = models.TextField()
    answer = models.TextField()
    sources = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class RepositoryChunk(models.Model):
    repository = models.ForeignKey(
        Repository,
        related_name="chunks",
        on_delete=models.CASCADE,
    )
    file = models.CharField(max_length=500)
    path = models.CharField(max_length=1000)
    chunk_id = models.PositiveIntegerField(default=0)
    start_line = models.PositiveIntegerField(null=True, blank=True)
    end_line = models.PositiveIntegerField(null=True, blank=True)
    preview = models.TextField()
    content = models.TextField()
    embedding = VectorField(dimensions=EMBEDDING_DIMENSION)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["path", "chunk_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "path", "chunk_id"],
                name="core_repochunk_repository_path_chunk_id_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["repository", "path"], name="core_repochunk_repo_path_idx"),
        ]

    def __str__(self):
        return f"{self.repository_id}:{self.path}#{self.chunk_id}"
