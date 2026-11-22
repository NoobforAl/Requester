"""The job-seeker side: candidate profiles, saved postings and job alerts."""

from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from employers.models import Currency, JobPosting, Skill, WorkMode

MIN_CANDIDATE_AGE = 16

phone_validator = RegexValidator(
    r"^\+?[0-9 ()-]{5,15}$",
    message=_("Enter a valid phone number (digits, spaces, + ( ) - only)."),
)


def validate_birth_date(value: date) -> None:
    today = date.today()
    if value > today:
        raise ValidationError(_("Date of birth cannot be in the future."))
    if value > today - timedelta(days=365 * MIN_CANDIDATE_AGE):
        raise ValidationError(
            _("Candidates must be at least %(age)d years old."),
            params={"age": MIN_CANDIDATE_AGE},
        )


class Candidate(models.Model):
    """A job seeker (formerly ``Worker``)."""

    class Education(models.TextChoices):
        HIGH_SCHOOL = "high_school", _("High school")
        ASSOCIATE = "associate", _("Associate degree")
        BACHELOR = "bachelor", _("Bachelor's degree")
        MASTER = "master", _("Master's degree")
        DOCTORATE = "doctorate", _("Doctorate")

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="candidate"
    )
    first_name = models.CharField(max_length=30, verbose_name=_("First name"))
    last_name = models.CharField(max_length=30, verbose_name=_("Last name"))
    # Copied onto User.email at registration (candidates/form.py); keep them in sync.
    email = models.EmailField(unique=True, verbose_name=_("Email"))
    phone_number = models.CharField(
        max_length=15,
        blank=True,
        default="",
        validators=[phone_validator],
        verbose_name=_("Phone number"),
    )
    address = models.TextField(blank=True, default="", verbose_name=_("Address"))
    date_of_birth = models.DateField(
        blank=True,
        null=True,
        validators=[validate_birth_date],
        verbose_name=_("Date of birth"),
    )
    headline = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name=_("Headline"),
        help_text=_("One line about you, e.g. “Backend developer, 5 years”."),
    )
    city = models.CharField(
        max_length=80, blank=True, default="", verbose_name=_("City")
    )
    skills = models.ManyToManyField(
        Skill, blank=True, related_name="candidates", verbose_name=_("Skills")
    )
    experience_years = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MaxValueValidator(60)],
        verbose_name=_("Years of experience"),
    )
    education_level = models.CharField(
        max_length=12,
        choices=Education,
        blank=True,
        default="",
        verbose_name=_("Education"),
    )
    expected_salary = models.PositiveIntegerField(
        blank=True, null=True, verbose_name=_("Expected salary")
    )
    expected_salary_currency = models.CharField(
        max_length=3,
        choices=Currency,
        default=Currency.IRR,
        verbose_name=_("Salary currency"),
    )
    preferred_work_mode = models.CharField(
        max_length=10,
        choices=WorkMode,
        blank=True,
        default="",
        verbose_name=_("Preferred work mode"),
    )
    linkedin_url = models.URLField(blank=True, default="", verbose_name=_("LinkedIn"))
    is_open_to_work = models.BooleanField(default=True, verbose_name=_("Open to work"))
    language = models.CharField(
        max_length=7,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        verbose_name=_("Preferred language"),
        help_text=_("Language of e-mails such as job alerts."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Candidate")
        verbose_name_plural = _("Candidates")
        constraints = (
            models.UniqueConstraint(Lower("email"), name="unique_candidate_email_ci"),
        )

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.user.username})"

    #: Profile fields that count towards the completeness bar on the dashboard.
    COMPLETENESS_FIELDS = (
        "phone_number",
        "headline",
        "city",
        "experience_years",
        "education_level",
        "expected_salary",
        "preferred_work_mode",
    )

    @property
    def profile_completeness(self) -> int:
        """Percentage (0-100) of the optional profile fields that are filled in."""
        filled = sum(
            1
            for name in self.COMPLETENESS_FIELDS
            if getattr(self, name) not in ("", None)
        )
        total = len(self.COMPLETENESS_FIELDS) + 1  # +1 for "at least one skill"
        if self.pk and self.skills.exists():
            filled += 1
        return round(100 * filled / total)


class SavedPosting(models.Model):
    """A posting a candidate bookmarked to look at later."""

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="saved_postings"
    )
    posting = models.ForeignKey(
        JobPosting, on_delete=models.CASCADE, related_name="saved_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Saved posting")
        verbose_name_plural = _("Saved postings")
        ordering = ("-created_at", "-id")
        constraints = (
            models.UniqueConstraint(
                fields=["candidate", "posting"], name="unique_saved_posting"
            ),
        )

    def __str__(self):
        return f"{self.candidate} saved {self.posting}"


class JobAlert(models.Model):
    """A saved search that e-mails the candidate when new postings match."""

    class Frequency(models.TextChoices):
        DAILY = "daily", _("Daily")
        WEEKLY = "weekly", _("Weekly")

    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="job_alerts"
    )
    name = models.CharField(max_length=80, verbose_name=_("Alert name"))
    keywords = models.CharField(
        max_length=120, blank=True, default="", verbose_name=_("Keywords")
    )
    location = models.CharField(
        max_length=80, blank=True, default="", verbose_name=_("City")
    )
    work_mode = models.CharField(
        max_length=10,
        choices=WorkMode,
        blank=True,
        default="",
        verbose_name=_("Work mode"),
    )
    employment_type = models.CharField(
        max_length=12,
        choices=JobPosting.EmploymentType,
        blank=True,
        default="",
        verbose_name=_("Employment type"),
    )
    min_salary = models.PositiveIntegerField(
        blank=True, null=True, verbose_name=_("Minimum salary")
    )
    skills = models.ManyToManyField(
        Skill, blank=True, related_name="job_alerts", verbose_name=_("Skills")
    )
    frequency = models.CharField(
        max_length=6,
        choices=Frequency,
        default=Frequency.DAILY,
        verbose_name=_("How often"),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    last_sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Job alert")
        verbose_name_plural = _("Job alerts")
        ordering = ("-created_at", "-id")
        indexes = (
            models.Index(
                fields=["is_active", "frequency"], name="alert_active_freq_idx"
            ),
        )

    def __str__(self):
        return f"{self.name} ({self.candidate})"

    def matching_postings(self):
        """Open postings that fit this alert (not yet limited to "new")."""
        return JobPosting.objects.open().search(
            self.keywords,
            location=self.location,
            work_mode=self.work_mode,
            employment_type=self.employment_type,
            min_salary=self.min_salary,
            skills=list(self.skills.all()),
        )
