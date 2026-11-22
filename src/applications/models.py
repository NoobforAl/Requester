"""A candidate's application to a job posting, and its status history."""

import uuid

from django.contrib.auth.models import User
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from candidates.models import Candidate
from employers.models import JobPosting


def resume_upload_to(instance: "Application", filename: str) -> str:
    """Store resumes under an unguessable name; the original name is never trusted."""
    return f"resumes/{instance.posting_id}__{uuid.uuid4().hex}.pdf"


class Application(models.Model):
    """A candidate applying to a posting (formerly ``JobRequest``)."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        IN_REVIEW = "in_review", _("In review")
        SHORTLISTED = "shortlisted", _("Shortlisted")
        ACCEPTED = "accepted", _("Accepted")
        REJECTED = "rejected", _("Rejected")
        WITHDRAWN = "withdrawn", _("Withdrawn")

    #: What an employer may change an application to, by current status.
    EMPLOYER_TRANSITIONS: dict[str, frozenset[str]] = {
        "pending": frozenset({"in_review", "shortlisted", "accepted", "rejected"}),
        "in_review": frozenset({"shortlisted", "accepted", "rejected"}),
        "shortlisted": frozenset({"in_review", "accepted", "rejected"}),
        "accepted": frozenset({"rejected"}),
        "rejected": frozenset({"in_review"}),
        "withdrawn": frozenset(),
    }
    #: Statuses from which the candidate may still withdraw.
    WITHDRAWABLE = frozenset({"pending", "in_review", "shortlisted"})

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="applications"
    )
    posting = models.ForeignKey(
        JobPosting, on_delete=models.CASCADE, related_name="applications"
    )
    resume = models.FileField(upload_to=resume_upload_to, verbose_name=_("Resume"))
    cover_letter = models.TextField(
        blank=True, default="", verbose_name=_("Cover letter")
    )
    status = models.CharField(
        max_length=20,
        choices=Status,
        default=Status.PENDING,
        verbose_name=_("Status"),
    )
    employer_note = models.TextField(
        blank=True, default="", verbose_name=_("Private note")
    )
    ai_summary = models.TextField(blank=True, default="", verbose_name=_("AI summary"))
    ai_provider = models.CharField(max_length=20, blank=True, default="")
    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Application")
        verbose_name_plural = _("Applications")
        ordering = ("-applied_at", "-id")
        indexes = (
            models.Index(fields=["posting", "status"], name="app_posting_status_idx"),
            models.Index(
                fields=["candidate", "-applied_at"], name="app_candidate_applied_idx"
            ),
        )
        constraints = (
            models.UniqueConstraint(
                fields=["candidate", "posting"], name="unique_candidate_posting"
            ),
        )

    def __str__(self):
        return f"Application by {self.candidate} for {self.posting}"

    def can_employer_set(self, status: str) -> bool:
        return status in self.EMPLOYER_TRANSITIONS.get(self.status, frozenset())

    def employer_status_choices(self) -> list[tuple[str, str]]:
        """The (value, label) statuses an employer may move this application to."""
        return [
            (value, str(label))
            for value, label in self.Status.choices
            if self.can_employer_set(value)
        ]

    @property
    def can_withdraw(self) -> bool:
        return self.status in self.WITHDRAWABLE

    def change_status(
        self, status: str, *, actor: User | None = None, note: str = ""
    ) -> "ApplicationEvent":
        """Move to ``status`` and log it, logging an event."""
        with transaction.atomic():
            event = ApplicationEvent.objects.create(
                application=self,
                from_status=self.status,
                to_status=status,
                actor=actor,
                note=note,
            )
            self.status = status
            self.save(update_fields=["status", "updated_at"])
        return event


class ApplicationEvent(models.Model):
    """One entry of an application's status history."""

    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="events"
    )
    from_status = models.CharField(max_length=20, choices=Application.Status)
    to_status = models.CharField(max_length=20, choices=Application.Status)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Application event")
        verbose_name_plural = _("Application events")
        ordering = ("created_at", "id")

    def __str__(self):
        return f"{self.application_id}: {self.from_status} -> {self.to_status}"
