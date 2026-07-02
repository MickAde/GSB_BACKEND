import uuid
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teaching', '0003_lessondocument_upload_fields'),
    ]

    operations = [
        # Remove the single-file field added in 0003
        migrations.RemoveField(
            model_name='lessondocument',
            name='uploaded_file',
        ),
        # Create the per-file child table
        migrations.CreateModel(
            name='LessonDocumentFile',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('file', models.FileField(upload_to='lesson_docs/uploads/')),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('document', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='uploaded_files',
                    to='teaching.lessondocument',
                )),
            ],
            options={
                'db_table': 'teaching_lessondocumentfile',
                'ordering': ['order', 'created_at'],
            },
        ),
    ]
