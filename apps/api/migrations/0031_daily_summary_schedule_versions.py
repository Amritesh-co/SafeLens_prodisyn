from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0030_eventcountsummary"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailalerttracker",
            name="daily_summary_schedule_version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="dailyincidentsummaryrecipient",
            name="last_sent_schedule_version",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
