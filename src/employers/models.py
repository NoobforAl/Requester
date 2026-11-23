"""The hiring side: employers, their job postings and the skills they use."""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Self

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Currency(models.TextChoices):
    IRR = "IRR", _("Iranian rial (IRR)")
    USD = "USD", _("US dollar (USD)")
    EUR = "EUR", _("Euro (EUR)")
    GBP = "GBP", _("Pound sterling (GBP)")
    RUB = "RUB", _("Russian ruble (RUB)")
    CNY = "CNY", _("Chinese yuan (CNY)")
    AED = "AED", _("UAE dirham (AED)")


class WorkMode(models.TextChoices):
    ONSITE = "onsite", _("On-site")
    HYBRID = "hybrid", _("Hybrid")
    REMOTE = "remote", _("Remote")


class Employer(models.Model):
    """A company that publishes job postings (formerly ``Offer``)."""

    class Size(models.TextChoices):
        TINY = "1-10", _("1-10 employees")
        SMALL = "11-50", _("11-50 employees")
        MEDIUM = "51-200", _("51-200 employees")
        LARGE = "201-1000", _("201-1000 employees")
        ENTERPRISE = "1000+", _("More than 1000 employees")

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, verbose_name=_("User"), related_name="employer"
    )
    name = models.CharField(max_length=100, verbose_name=_("Company name"))
    contact_email = models.EmailField(unique=True, verbose_name=_("Company email"))
    description = models.TextField(
        blank=True, default="", verbose_name=_("Description")
    )
    website = models.URLField(blank=True, default="", verbose_name=_("Website"))
    industry = models.CharField(
        max_length=80, blank=True, default="", verbose_name=_("Industry")
    )
    size = models.CharField(
        max_length=10,
        choices=Size,
        blank=True,
        default="",
        verbose_name=_("Company size"),
    )
    city = models.CharField(
        max_length=80, blank=True, default="", verbose_name=_("City")
    )
    language = models.CharField(
        max_length=7,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        verbose_name=_("Preferred language"),
        help_text=_("Language of reports and e-mails sent to the company."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Employer")
        verbose_name_plural = _("Employers")
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                Lower("contact_email"), name="unique_employer_contact_email_ci"
            ),
        )

    def __str__(self):
        return f"{self.user.username} ({self.name})"


class Skill(models.Model):
    """A skill or topic that postings ask for and candidates have (formerly ``Tag``)."""

    name = models.CharField(max_length=50, unique=True, verbose_name=_("Skill name"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Skill")
        verbose_name_plural = _("Skills")
        ordering = ("name",)

    def __str__(self):
        return self.name


class JobPostingQuerySet(models.QuerySet["JobPosting"]):
    def open(self) -> Self:
        """Postings a candidate can still apply to: active and not past the deadline."""
        return self.filter(is_active=True).filter(
            Q(deadline__isnull=True) | Q(deadline__gte=timezone.localdate())
        )

    def search(  # noqa: PLR0913 - one keyword per filter on the job list
        self,
        query: str = "",
        *,
        location: str = "",
        work_mode: str = "",
        employment_type: str = "",
        seniority: str = "",
        min_salary: int | None = None,
        skills: Iterable["Skill | int"] = (),
        remote_only: bool = False,
    ) -> Self:
        """Filter the list shown to candidates. Blank filters are ignored."""
        postings = self
        query = query.strip()
        if query:
            postings = postings.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(employer__name__icontains=query)
            )
        if location.strip():
            postings = postings.filter(location__icontains=location.strip())
        if remote_only:
            work_mode = WorkMode.REMOTE
        if work_mode:
            postings = postings.filter(work_mode=work_mode)
        if employment_type:
            postings = postings.filter(employment_type=employment_type)
        if seniority:
            postings = postings.filter(seniority=seniority)
        if min_salary:
            postings = postings.filter(
                Q(salary_max__gte=min_salary)
                | Q(salary_max__isnull=True, salary_min__gte=min_salary)
            )
        skill_ids = [
            skill.pk if isinstance(skill, Skill) else skill for skill in skills
        ]
        if skill_ids:
            postings = postings.filter(skills__in=skill_ids).distinct()
        return postings


class JobPostingManager(models.Manager["JobPosting"]):
    """``JobPosting.objects``: the queryset methods, also on the manager.

    A real class instead of ``JobPostingQuerySet.as_manager()``: that one is built
    at runtime, so editors without the django-stubs mypy plugin (Pylance/Pyright)
    reported "Cannot access attribute 'open'". Related managers
    (``employer.postings``) are subclasses of this one and get the methods too.
    """

    def get_queryset(self) -> JobPostingQuerySet:
        return JobPostingQuerySet(self.model, using=self._db)

    def open(self) -> JobPostingQuerySet:
        return self.get_queryset().open()

    def search(  # noqa: PLR0913 - same keywords as JobPostingQuerySet.search
        self,
        query: str = "",
        *,
        location: str = "",
        work_mode: str = "",
        employment_type: str = "",
        seniority: str = "",
        min_salary: int | None = None,
        skills: Iterable["Skill | int"] = (),
        remote_only: bool = False,
    ) -> JobPostingQuerySet:
        return self.get_queryset().search(
            query,
            location=location,
            work_mode=work_mode,
            employment_type=employment_type,
            seniority=seniority,
            min_salary=min_salary,
            skills=skills,
            remote_only=remote_only,
        )


class JobPosting(models.Model):
    """A job an employer is hiring for (formerly ``Job``)."""

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", _("Full-time")
        PART_TIME = "part_time", _("Part-time")
        CONTRACT = "contract", _("Contract")
        INTERNSHIP = "internship", _("Internship")
        FREELANCE = "freelance", _("Freelance")

    class Seniority(models.TextChoices):
        INTERN = "intern", _("Intern")
        JUNIOR = "junior", _("Junior")
        MID = "mid", _("Mid-level")
        SENIOR = "senior", _("Senior")
        LEAD = "lead", _("Lead / Manager")

    title = models.CharField(max_length=100, verbose_name=_("Job title"))
    description = models.TextField(verbose_name=_("Description"))
    skills = models.ManyToManyField(
        Skill, blank=True, related_name="postings", verbose_name=_("Skills")
    )
    employer = models.ForeignKey(
        Employer,
        on_delete=models.CASCADE,
        related_name="postings",
        verbose_name=_("Employer"),
    )
    location = models.CharField(
        max_length=80, blank=True, default="", db_index=True, verbose_name=_("City")
    )
    country = models.CharField(
        max_length=80, blank=True, default="", verbose_name=_("Country")
    )
    work_mode = models.CharField(
        max_length=10,
        choices=WorkMode,
        default=WorkMode.ONSITE,
        verbose_name=_("Work mode"),
    )
    employment_type = models.CharField(
        max_length=12,
        choices=EmploymentType,
        default=EmploymentType.FULL_TIME,
        verbose_name=_("Employment type"),
    )
    seniority = models.CharField(
        max_length=10,
        choices=Seniority,
        blank=True,
        default="",
        verbose_name=_("Seniority"),
    )
    salary_min = models.PositiveIntegerField(
        blank=True, null=True, verbose_name=_("Minimum salary")
    )
    salary_max = models.PositiveIntegerField(
        blank=True, null=True, verbose_name=_("Maximum salary")
    )
    salary_currency = models.CharField(
        max_length=3,
        choices=Currency,
        default=Currency.IRR,
        verbose_name=_("Salary currency"),
    )
    deadline = models.DateField(
        blank=True, null=True, verbose_name=_("Application deadline")
    )
    is_active = models.BooleanField(
        default=True, verbose_name=_("Accepting applications")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = JobPostingManager()

    # Added by Django at runtime. Declared for editors without the django-stubs mypy
    # plugin (Pylance/Pyright); the annotations do not create fields.
    id: int
    employer_id: int
    if TYPE_CHECKING:
        # Set per row by the candidate job list (candidates.views.Postings).
        match: int
        is_saved: bool

    class Meta:
        verbose_name = _("Job posting")
        verbose_name_plural = _("Job postings")
        ordering = ("-created_at", "-id")
        indexes = (
            models.Index(
                fields=["employer", "-created_at"], name="posting_employer_created_idx"
            ),
            models.Index(
                fields=["is_active", "-created_at"], name="posting_active_created_idx"
            ),
            models.Index(fields=["work_mode"], name="posting_work_mode_idx"),
            models.Index(fields=["employment_type"], name="posting_type_idx"),
        )
        constraints = (
            models.UniqueConstraint(
                fields=["title", "employer"], name="unique_posting_title_per_employer"
            ),
            models.CheckConstraint(
                condition=Q(salary_min__isnull=True)
                | Q(salary_max__isnull=True)
                | Q(salary_min__lte=F("salary_max")),
                name="posting_salary_min_lte_max",
            ),
        )

    def __str__(self):
        return f"{self.title} @ {self.employer.name}"

    @property
    def is_open(self) -> bool:
        """True while a candidate can still apply."""
        if not self.is_active:
            return False
        return self.deadline is None or self.deadline >= timezone.localdate()
