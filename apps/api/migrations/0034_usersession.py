import secrets

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0033_alter_userprofile_role"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserSession",
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
                (
                    "token",
                    models.CharField(
                        db_index=True,
                        default=secrets.token_hex,
                        editable=False,
                        max_length=64,
                        unique=True,
                    ),
                ),
                (
                    "login_time",
                    models.DateTimeField(
                        auto_now_add=True
                    ),
                ),
                (
                    "logout_time",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "ip_address",
                    models.GenericIPAddressField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "user_agent",
                    models.TextField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auth_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "user_sessions",
                "ordering": ["-login_time"],
                "indexes": [
                    models.Index(
                        fields=[
                            "user",
                            "logout_time",
                            "login_time",
                        ],
                        name="us_user_logout_login_idx",
                    ),
                    models.Index(
                        fields=[
                            "user",
                            "login_time",
                        ],
                        name="us_user_login_idx",
                    ),
                ],
            },
        ),
    ]