# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-08-16 10:16
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0054_track_foreground_color'),
    ]

    operations = [
        migrations.AddField(
            model_name='conference',
            name='cardsactive',
            field=models.BooleanField(default=False, help_text='Publish "cards" for sessions and speakers', verbose_name='Card publishing active'),
        ),
    ]
