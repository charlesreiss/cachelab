# Generated by Django 2.0.2 on 2018-03-18 20:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0007_parameteranswer_was_save'),
    ]

    operations = [
        migrations.AlterField(
            model_name='patternquestion',
            name='give_first',
            field=models.IntegerField(default=6),
        ),
    ]
