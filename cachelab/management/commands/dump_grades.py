from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import Permission, User
from django.db import IntegrityError

from cachelab.views import make_score_csv

import datetime
import sys

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--deadline')
        parser.add_argument('--exceptions', default='')

    def handle(self, *args, **options):
        due_date = datetime.datetime.strptime(options['deadline'], '%Y-%m-%dT%H:%M:%S%z')
        due_exceptions = {}
        for item in options['exceptions'].split(','):
            if item == '':
                continue
            user, cur_date = item.split('=', 1)
            due_exceptions[user] = datetime.datetime.strptime(cur_date, '%Y-%m-%dT%H:%M:%S%z')
        make_score_csv(sys.stdout, due_date, due_exceptions)
