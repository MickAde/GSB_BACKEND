from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teaching', '0002_add_lesson_document'),
    ]

    operations = [
        migrations.AddField(
            model_name='lessondocument',
            name='uploaded_file',
            field=models.FileField(blank=True, null=True, upload_to='lesson_docs/uploads/'),
        ),
        migrations.AddField(
            model_name='lessondocument',
            name='raw_ocr_text',
            field=models.TextField(blank=True),
        ),
    ]
