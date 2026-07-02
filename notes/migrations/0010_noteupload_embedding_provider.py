from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0009_conformity_history'),
    ]

    operations = [
        migrations.AddField(
            model_name='noteupload',
            name='embedding_provider',
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
