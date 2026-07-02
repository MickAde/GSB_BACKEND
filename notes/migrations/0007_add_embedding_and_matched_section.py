from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0006_add_extra_file_urls'),
    ]

    operations = [
        migrations.AddField(
            model_name='noteupload',
            name='embedding',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='noteconformityreport',
            name='matched_teacher_section',
            field=models.TextField(blank=True, default=''),
            preserve_default=False,
        ),
    ]
