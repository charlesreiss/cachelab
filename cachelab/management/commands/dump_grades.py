from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import Permission, User
from django.db import IntegrityError

from cachelab.views import make_score_csv

import datetime
from dateutil.parser import isoparse
import sys

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--deadline')
        parser.add_argument('--exceptions', default='')

    def handle(self, *args, **options):
        due_date = isoparse(options['deadline'])
        due_exceptions = {}
        for item in options['exceptions'].split(','):
            if item == '':
                continue
            user, cur_date = item.split('=', 1)
            due_exceptions[user] = isoparse(cur_date)
        make_score_csv(sys.stdout, due_date, due_exceptions)
