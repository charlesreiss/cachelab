from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import Permission, User

from cachelab.models import StaffUser

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
            staff_user = StaffUser.get(user=user)
            staff_user.delete()
        except ObjectDoesNotExist:
            print("User", username, "was already not staff")
            return
        print("Marked user", username, "as not staff")
