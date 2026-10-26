from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('term_list', '0007_dailysalt_metadatasearchtrack_visitor_hash'),
    ]

    operations = [
        migrations.AddField(
            model_name='metadatasearchtrack',
            name='country',
            field=models.CharField(blank=True, max_length=2, null=True),
        ),
    ]
