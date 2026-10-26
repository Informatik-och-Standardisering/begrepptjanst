from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('term_list', '0006_alter_attribute_options_alter_attributevalue_options_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailySalt',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('salt', models.CharField(max_length=64)),
            ],
        ),
        migrations.AddField(
            model_name='metadatasearchtrack',
            name='visitor_hash',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
