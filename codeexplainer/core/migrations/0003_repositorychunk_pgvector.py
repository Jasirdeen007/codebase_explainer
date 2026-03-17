# Generated manually for pgvector-backed repository chunk storage.

import django.db.models.deletion
from django.db import migrations, models

import core.fields


def create_vector_extension(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS vector")


def create_vector_index(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            """
            CREATE INDEX IF NOT EXISTS core_repochunk_embedding_hnsw_idx
            ON core_repositorychunk
            USING hnsw (embedding vector_cosine_ops)
            """
        )


def drop_vector_index(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS core_repochunk_embedding_hnsw_idx")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_repository_indexing_fields_and_chat_sources"),
    ]

    operations = [
        migrations.RunPython(create_vector_extension, migrations.RunPython.noop),
        migrations.CreateModel(
            name="RepositoryChunk",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("file", models.CharField(max_length=500)),
                ("path", models.CharField(max_length=1000)),
                ("chunk_id", models.PositiveIntegerField(default=0)),
                ("start_line", models.PositiveIntegerField(blank=True, null=True)),
                ("end_line", models.PositiveIntegerField(blank=True, null=True)),
                ("preview", models.TextField()),
                ("content", models.TextField()),
                ("embedding", core.fields.VectorField(dimensions=384)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "repository",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="core.repository",
                    ),
                ),
            ],
            options={
                "ordering": ["path", "chunk_id"],
                "indexes": [
                    models.Index(
                        fields=["repository", "path"],
                        name="core_repochunk_repo_path_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("repository", "path", "chunk_id"),
                        name="core_repochunk_repository_path_chunk_id_uniq",
                    )
                ],
            },
        ),
        migrations.RunPython(create_vector_index, drop_vector_index),
    ]
