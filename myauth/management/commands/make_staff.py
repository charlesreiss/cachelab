from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import Permission, User
from django.db import IntegrityError

from myauth.models import StaffUser

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('username')

    def handle(self, *args, **options):
        username = options['username']
        try:
            user = User.objects.get(username=username)
        except ObjectDoesNotExist:
            print("User", username, "does not exist")
            return
        try:
            staff_user = StaffUser(user=user)
            staff_user.save()
        except IntegrityError:
            print("User", username, "already staff")
            return
        print("Marked user", username, "as staff")
