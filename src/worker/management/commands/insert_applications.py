import os
import random

from django.core.management.base import BaseCommand

from offer.models import Job
from worker.models import Worker, JobRequest


class Command(BaseCommand):
    help = 'Insert multiple job requests for each worker'

    def handle(self, *args, **options):
        workers = Worker.objects.all()
        jobs = Job.objects.all()

        if not jobs.exists():
            self.stdout.write(self.style.ERROR(
                'No jobs found in the database.'))
            return

        resumePath = 'resumes/resume.pdf'
        if not os.path.exists(resumePath):
            open(resumePath, 'w').close()

        if JobRequest.objects.count() > 0:
            self.stdout.write(
                self.style.ERROR('Job requests already exist in the database.')
            )
            return

        for worker in workers:
            # Random number of requests per worker
            num_requests = random.randint(1, 5)
            for _ in range(num_requests):
                job = random.choice(jobs)
                JobRequest.objects.get_or_create(
                    worker=worker,
                    job=job,
                    defaults={
                        'resume': resumePath,
                        'cover_letter': (
                            'من برای این کار '
                            'مناسب هستم زیرا تجربه و مهارت‌های لازم را دارم.'
                        ),
                        'status': 'pending',
                    }
                )
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully added job request for worker: '
                    f'{worker.user.username} for job: {job.job_name}'
                ))
