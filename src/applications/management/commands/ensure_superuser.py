import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Create the admin user from DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD. "
        "Does nothing when the password is unset or the user already exists."
    )

    def handle(self, *args, **options):
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if not password:
            self.stdout.write(
                self.style.WARNING(
                    "DJANGO_SUPERUSER_PASSWORD is not set: no admin user created."
                )
            )
            return

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            self.stdout.write(f"Admin user '{username}' already exists; left as is.")
            return

        user_model.objects.create_superuser(username, email, password)
        self.stdout.write(self.style.SUCCESS(f"Admin user '{username}' created."))
