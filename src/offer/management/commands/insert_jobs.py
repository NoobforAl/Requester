from django.core.management.base import BaseCommand
from offer.models import Job, Offer, Tag


class Command(BaseCommand):
    help = 'Insert multiple jobs into the database'

    def handle(self, *args, **kwargs):
        jobs_to_insert = [
            {
                'job_name': 'Software Engineer',
                'detail': 'Develop and maintain software applications.',
                'tags': ['development', 'software', 'engineer'],
                'offer': 'alice'
            },
            {
                'job_name': 'Data Scientist',
                'detail': 'Analyze and interpret complex data sets.',
                'tags': ['data', 'science', 'analytics'],
                'offer': 'bob',
            },
            {
                'job_name': 'Project Manager',
                'detail': 'Manage projects and ensure timely delivery.',
                'tags': ['management', 'leadership', 'projects'],
                'offer': 'charlie',
            },
            {
                'job_name': 'DevOps Engineer',
                'detail': 'Work on CI/CD and cloud infrastructure.',
                'tags': ['devops', 'cloud', 'infrastructure'],
                'offer': 'dave',
            },
            {
                'job_name': 'UI/UX Designer',
                'detail': 'Design user-friendly interfaces.',
                'tags': ['design', 'ui', 'ux'],
                'offer': 'eve',
            },
            {
                'job_name': 'Frontend Developer',
                'detail': 'Build responsive web applications.',
                'tags': ['frontend', 'javascript', 'react'],
                'offer': 'frank',
            },
            {
                'job_name': 'Backend Developer',
                'detail': 'Create and maintain server-side applications.',
                'tags': ['backend', 'python', 'django'],
                'offer': 'grace',
            },
            {
                'job_name': 'Mobile Developer',
                'detail': 'Develop applications for mobile platforms.',
                'tags': ['mobile', 'android', 'ios'],
                'offer': 'heidi',
            },
            {
                'job_name': 'System Administrator',
                'detail': 'Manage and maintain IT infrastructure.',
                'tags': ['sysadmin', 'infrastructure', 'networking'],
                'offer': 'ivan',
            },
            {
                'job_name': 'Cybersecurity Analyst',
                'detail': 'Protect systems from security breaches.',
                'tags': ['security', 'cybersecurity', 'analysis'],
                'offer': 'judy',
            },
        ]

        for job_data in jobs_to_insert:
            offer = Offer.objects.filter(
                user__username=job_data['offer']).first()
            if not offer:
                self.stdout.write(self.style.ERROR(
                    f'Offer not found for user: {job_data["offer"]}'))
                continue

            tag_objects = []
            for tag_name in job_data['tags']:
                tag, created = Tag.objects.get_or_create(name=tag_name)
                tag_objects.append(tag)

            job, created = Job.objects.get_or_create(
                job_name=job_data['job_name'],
                offer=offer,
                defaults={
                    'detail': job_data['detail'],
                }
            )

            job.tags.set(tag_objects)

            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully added job: {job_data["job_name"]}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Job already exists: {job_data["job_name"]}'))
