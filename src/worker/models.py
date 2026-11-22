import uuid

from django.contrib.auth.models import User
from django.db import models
from django.db.models.functions import Lower

from offer.models import Job


def resume_upload_to(instance: "JobRequest", filename: str) -> str:
    """Store resumes under an unguessable name; the original name is never trusted."""
    return f"resumes/{instance.job_id}__{uuid.uuid4().hex}.pdf"


class Worker(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    # Copied onto User.email at registration (worker/form.py); keep them in sync.
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, blank=True, default="")
    address = models.TextField(blank=True, default="")
    date_of_birth = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Worker"
        verbose_name_plural = "Workers"
        constraints = (
            models.UniqueConstraint(Lower("email"), name="unique_worker_email_ci"),
        )

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.user.username})"


class JobRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        ACCEPTED = "accepted", "پذیرفته شده"
        REJECTED = "rejected", "رد شده"

    worker = models.ForeignKey(Worker, on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    resume = models.FileField(upload_to=resume_upload_to)
    cover_letter = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status,
        default=Status.PENDING,
    )
    ai_summary = models.TextField(blank=True, default="")
    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Job Request"
        verbose_name_plural = "Job Requests"
        ordering = ("-applied_at", "-id")
        indexes = (
            models.Index(fields=["job", "status"], name="jobreq_job_status_idx"),
            models.Index(
                fields=["worker", "-applied_at"], name="jobreq_worker_applied_idx"
            ),
        )
        constraints = (
            models.UniqueConstraint(
                fields=["worker", "job"], name="unique_worker_job_request"
            ),
        )

    def __str__(self):
        return f"Job Request by {self.worker} for {self.job}"
