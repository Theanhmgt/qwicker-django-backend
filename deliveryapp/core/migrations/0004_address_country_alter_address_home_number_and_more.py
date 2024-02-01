# Generated by Django 5.0 on 2024-01-28 03:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_remove_payment_payment_method_alter_payment_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='address',
            name='country',
            field=models.CharField(default='abc', max_length=20),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='address',
            name='home_number',
            field=models.CharField(max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='address',
            name='street',
            field=models.CharField(max_length=50, null=True),
        ),
    ]