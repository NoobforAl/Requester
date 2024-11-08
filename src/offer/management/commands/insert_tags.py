from django.core.management.base import BaseCommand
from offer.models import Tag


class Command(BaseCommand):
    help = 'Insert predefined tags into the database'

    def handle(self, *args, **kwargs):
        tags = [
            "Django",
            "Python",
            "Software Engineer",
            "Data Scientist",
            "Web Developer",
            "Backend Developer",
            "Frontend Developer",
            "Full Stack Developer",
            "DevOps Engineer",
            "Machine Learning Engineer",
            "System Administrator",
            "Database Administrator",
            "Software Architect",
            "QA Engineer",
            "Mobile Developer",
            "UX/UI Designer",
            "Product Manager",
            "Technical Writer",
            "IT Support Specialist",
            "Network Engineer",
            "Cloud Engineer",
        ]

        for tag_name in tags:
            tag, created = Tag.objects.get_or_create(name=tag_name)

            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully added tag: {tag_name}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Tag already exists: {tag_name}'))
