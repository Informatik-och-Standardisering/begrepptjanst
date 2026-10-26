from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('term_list', '0009_fill_visitor_hash_and_country_from_ip'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='metadatasearchtrack',
            name='ip_adress',
        ),
        migrations.RemoveField(
            model_name='searchtrack',
            name='ip_adress',
        ),
    ]
