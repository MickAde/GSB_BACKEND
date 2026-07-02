from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0002_quiz_settings'),
        ('teaching', '0002_add_lesson_document'),
    ]

    operations = [
        migrations.AddField(
            model_name='quiz',
            name='lesson_doc',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='quizzes',
                to='teaching.lessondocument',
            ),
        ),
    ]
