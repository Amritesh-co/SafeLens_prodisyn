

from django.db import migrations, models


def support_to_supervisor(apps, schema_editor):
    UserProfile = apps.get_model("api", "UserProfile")
    UserProfile.objects.filter(role="Support").update(role="Supervisor")


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0032_eventcountsummary_all_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("Admin", "Admin"),
                    ("Management", "Management"),
                    ("Manager", "Manager"),
                    ("Supervisor", "Supervisor"),
                ],
                default="Supervisor",
                max_length=20,
            ),
        ),
        migrations.RunPython(support_to_supervisor, migrations.RunPython.noop),
    ]