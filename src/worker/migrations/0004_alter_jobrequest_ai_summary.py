# Generated by Django 5.1 on 2024-12-22 12:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worker', '0003_jobrequest_ai_summary'),
    ]

    operations = [
        migrations.AlterField(
            model_name='jobrequest',
            name='ai_summary',
            field=models.TextField(blank=True, default='', null=True),
        ),
    ]
