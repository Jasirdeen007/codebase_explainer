# Generated manually for repository indexing/status enhancements.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="repository",
            name="error_message",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="repository",
            name="index_path",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="repository",
            name="status",
            field=models.CharField(
                choices=[
                    ("processing", "Processing"),
                    ("ready", "Ready"),
                    ("failed", "Failed"),
                ],
                default="processing",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="repository",
            name="total_chunks",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="repository",
            name="total_files",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="chatmessage",
            name="repository",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="messages",
                to="core.repository",
            ),
        ),
        migrations.AddField(
            model_name="chatmessage",
            name="sources",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
