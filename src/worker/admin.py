from django.contrib import admin

from worker.models import JobRequest, Worker

# Register your models here.
admin.site.register(Worker)
admin.site.register(JobRequest)
