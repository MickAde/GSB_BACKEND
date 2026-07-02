from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0007_add_embedding_and_matched_section'),
        ('teaching', '0002_add_lesson_document'),
    ]

    operations = [
        # Make teacher_note nullable so records can use teacher_lesson_doc instead
        migrations.AlterField(
            model_name='noteconformityreport',
            name='teacher_note',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='conformity_reports_as_teacher',
                to='notes.noteupload',
            ),
        ),
        # Add FK to LessonDocument as alternative teacher reference
        migrations.AddField(
            model_name='noteconformityreport',
            name='teacher_lesson_doc',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='conformity_reports',
                to='teaching.lessondocument',
            ),
        ),
    ]
