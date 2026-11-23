from datetime import date, datetime, time

import structlog
from django.contrib import messages
from django.core.paginator import Page, Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import FileResponse, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import redirect, render
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.views import View

from applications.models import Application
from applications.tasks import notify_status_change, send_posting_report
from requester.localdates import format_day, month_starts
from requester.portal import (
    AuthenticatedRequest,
    PortalAccessMixin,
    PortalLoginView,
    PortalLogoutView,
    PortalRegisterView,
)

from .form import (
    EmployerUpdateForm,
    JobPostingForm,
    UserLoginForm,
    UserRegistrationForm,
)
from .models import Employer, JobPosting

logger = structlog.get_logger(__name__)

POSTING_NOT_FOUND = _("This job posting was not found. It may have been deleted.")
FORM_INVALID = _("Nothing was saved. Fix the form errors.")
APPLICATION_NOT_FOUND = _("This application was not found.")


def start_of_day(day: date) -> datetime:
    """Midnight at the start of ``day`` in the current time zone."""
    return timezone.make_aware(datetime.combine(day, time.min))


class EmployerAccessMixin(PortalAccessMixin):
    """Employer-only views. Every query below is scoped to ``employer_of(req)``."""

    portal = "employer"


def employer_of(req: AuthenticatedRequest) -> Employer:
    """The signed-in user's profile (``EmployerAccessMixin`` checked that it exists).

    ``user.employer`` is the reverse one-to-one Django adds at runtime: mypy's
    django-stubs plugin knows it, Pylance/Pyright do not.
    """
    return req.user.employer  # pyright: ignore[reportAttributeAccessIssue]


class Login(PortalLoginView):
    portal = "employer"
    template_name = "employers/login.html"
    form_class = UserLoginForm


class Logout(PortalLogoutView):
    portal = "employer"


class Register(PortalRegisterView):
    portal = "employer"
    template_name = "employers/register.html"
    form_class = UserRegistrationForm


class Dashboard(EmployerAccessMixin, View):
    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        employer = employer_of(req)
        language = translation.get_language()
        postings = JobPosting.objects.filter(employer=employer)
        applications = Application.objects.filter(posting__employer=employer)

        this_month, last_month = month_starts(timezone.localdate(), language)
        current_start = start_of_day(this_month)
        last_start = start_of_day(last_month)

        applications_per_day = (
            applications.filter(applied_at__gte=current_start)
            .annotate(day=TruncDate("applied_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        per_day = [
            {"day": format_day(item["day"], language), "count": item["count"]}
            for item in applications_per_day
        ]
        by_status = applications.aggregate(
            pending=Count("id", filter=Q(status=Application.Status.PENDING)),
            in_review=Count("id", filter=Q(status=Application.Status.IN_REVIEW)),
            shortlisted=Count("id", filter=Q(status=Application.Status.SHORTLISTED)),
        )

        return render(
            req,
            "employers/dashboard.html",
            {
                "num_of_postings": postings.count(),
                "num_of_open_postings": JobPosting.objects.open()
                .filter(employer=employer)
                .count(),
                "num_of_applications": applications.count(),
                "postings_current_month": postings.filter(
                    created_at__gte=current_start
                ).count(),
                "postings_last_month": postings.filter(
                    created_at__gte=last_start, created_at__lt=current_start
                ).count(),
                "applications_per_day": per_day,
                "applications_per_day_max": max(
                    (item["count"] for item in per_day), default=1
                ),
                "to_review": by_status["pending"],
                "in_review": by_status["in_review"],
                "shortlisted": by_status["shortlisted"],
            },
        )


class Settings(EmployerAccessMixin, View):
    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        form = EmployerUpdateForm(instance=employer_of(req))
        return render(req, "employers/settings.html", {"form": form})

    def post(self, req: AuthenticatedRequest) -> HttpResponse:
        form = EmployerUpdateForm(req.POST, instance=employer_of(req))
        if form.is_valid():
            form.save()
            messages.success(req, _("Company details saved."))
            return redirect("employer_settings")

        messages.error(req, FORM_INVALID)
        return render(req, "employers/settings.html", {"form": form})


class Postings(EmployerAccessMixin, View):
    """List the employer's postings and create a new one."""

    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        return render(
            req,
            "employers/jobs.html",
            {
                "form": JobPostingForm(),
                "postings": self._page(req, req.GET.get("page")),
            },
        )

    def post(self, req: AuthenticatedRequest) -> HttpResponse:
        employer = employer_of(req)
        form = JobPostingForm(req.POST, employer=employer)
        if form.is_valid():
            posting = form.save(commit=False)
            posting.employer = employer
            posting.save()
            form.save_m2m()
            messages.success(req, _("Job posting created."))
            return redirect("employer_jobs")

        messages.error(req, FORM_INVALID)
        return render(
            req,
            "employers/jobs.html",
            {"postings": self._page(req, 1), "form": form},
        )

    @staticmethod
    def _page(req: AuthenticatedRequest, number: int | str | None) -> Page:
        postings = (
            JobPosting.objects.filter(employer=employer_of(req))
            .annotate(application_count=Count("applications"))
            .order_by("-created_at", "-id")
        )
        return Paginator(postings.prefetch_related("skills"), 10).get_page(number)


class OwnedPostingMixin(EmployerAccessMixin):
    """Looks up a posting, but only one that belongs to the signed-in employer."""

    @staticmethod
    def get_posting(req: AuthenticatedRequest, pk: int) -> JobPosting | None:
        return JobPosting.objects.filter(pk=pk, employer=employer_of(req)).first()


class PostingDetail(OwnedPostingMixin, View):
    def get(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        posting = self.get_posting(req, pk)
        if posting is None:
            messages.error(req, POSTING_NOT_FOUND)
            return redirect("employer_jobs")

        search_query = req.GET.get("search", "").strip()
        status = req.GET.get("status", "")
        applications = (
            Application.objects.filter(posting=posting)
            .select_related("candidate")
            .order_by("applied_at")
        )
        if search_query:
            applications = applications.filter(
                Q(candidate__first_name__icontains=search_query)
                | Q(candidate__last_name__icontains=search_query)
                | Q(candidate__email__icontains=search_query)
            )
        if status in Application.Status.values:
            applications = applications.filter(status=status)

        applications_page = Paginator(applications, 10).get_page(req.GET.get("page"))
        return render(
            req,
            "employers/job.html",
            {
                "form": JobPostingForm(instance=posting),
                "posting": posting,
                "applications": applications_page,
                "search_query": search_query,
                "status_filter": status,
                "statuses": Application.Status.choices,
            },
        )


class PostingEdit(OwnedPostingMixin, View):
    """POST only: the edit form lives on the posting page."""

    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        posting = self.get_posting(req, pk)
        if posting is None:
            messages.error(req, POSTING_NOT_FOUND)
            return redirect("employer_jobs")

        form = JobPostingForm(req.POST, instance=posting, employer=employer_of(req))
        if form.is_valid():
            form.save()
            messages.success(req, _("Job posting updated."))
        else:
            messages.error(req, FORM_INVALID)
        return redirect("employer_job", pk=posting.pk)


class PostingToggle(OwnedPostingMixin, View):
    """Close a posting to new applications, or open it again."""

    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        posting = self.get_posting(req, pk)
        if posting is None:
            messages.error(req, POSTING_NOT_FOUND)
            return redirect("employer_jobs")

        posting.is_active = not posting.is_active
        posting.save(update_fields=["is_active", "updated_at"])
        if posting.is_active:
            messages.success(req, _("The posting is open for applications again."))
        else:
            messages.success(req, _("The posting is closed to new applications."))
        return redirect("employer_job", pk=posting.pk)


class PostingDelete(OwnedPostingMixin, View):
    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        posting = self.get_posting(req, pk)
        if posting is None:
            messages.error(req, POSTING_NOT_FOUND)
        else:
            posting.delete()
            messages.success(req, _("Job posting deleted."))
        return redirect("employer_jobs")


class PostingReport(OwnedPostingMixin, View):
    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        posting = self.get_posting(req, pk)
        if posting is None:
            messages.error(req, POSTING_NOT_FOUND)
            return redirect("employer_jobs")

        send_posting_report.delay(posting.pk)
        messages.warning(
            req,
            _(
                "Report requested. It is e-mailed to your company address "
                "within three working days."
            ),
        )
        return redirect("employer_jobs")


class OwnedApplicationMixin(EmployerAccessMixin):
    """Looks up an application, but only one for a posting of the signed-in employer."""

    def get_application(self, req: AuthenticatedRequest, pk: int) -> Application | None:
        return (
            Application.objects.select_related("posting")
            .filter(pk=pk, posting__employer=employer_of(req))
            .first()
        )


class ResumeDownload(OwnedApplicationMixin, View):
    def get(self, req: AuthenticatedRequest, pk: int) -> HttpResponseBase:
        application = self.get_application(req, pk)
        if application is None:
            messages.error(req, APPLICATION_NOT_FOUND)
            return redirect("employer_jobs")

        try:
            return FileResponse(
                application.resume.open("rb"),
                content_type="application/pdf",
                filename=f"resume_{application.pk}.pdf",
            )
        except (FileNotFoundError, ValueError):
            messages.error(
                req,
                _("The resume file was not found. Ask the candidate to apply again."),
            )
            return redirect("employer_job", pk=application.posting_id)


class ApplicationStatusUpdate(OwnedApplicationMixin, View):
    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        application = self.get_application(req, pk)
        if application is None:
            messages.error(req, APPLICATION_NOT_FOUND)
            return redirect("employer_jobs")

        status = req.POST.get("status", "")
        note = req.POST.get("note", "").strip()[:500]
        if status not in Application.Status.values:
            messages.error(req, _("The selected status is not valid."))
        elif not application.can_employer_set(status):
            messages.error(req, _("This status change is not allowed."))
        else:
            application.change_status(status, actor=req.user, note=note)
            try:
                notify_status_change.delay(application.pk)
            except Exception:
                # The change is saved; only the candidate's e-mail is delayed.
                logger.exception(
                    "status_email_queue_failed", application_id=application.pk
                )
            messages.success(req, _("Application status updated."))
        return redirect("employer_job", pk=application.posting_id)
