import structlog
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views import View

from applications.models import Application
from applications.tasks import summarize_application
from employers.models import JobPosting
from requester.portal import (
    AuthenticatedRequest,
    PortalAccessMixin,
    PortalLoginView,
    PortalLogoutView,
    PortalRegisterView,
)

from .alerts import alert_from_token
from .form import (
    JobAlertForm,
    JobFilterForm,
    ProfileForm,
    ResumeUploadForm,
    UserLoginForm,
    UserRegistrationForm,
)
from .matching import candidate_skill_ids, match_score
from .models import JobAlert, SavedPosting

logger = structlog.get_logger(__name__)

POSTING_NOT_FOUND = _("This job posting was not found. It may have been deleted.")
ALREADY_APPLIED = _("You have already applied for this job.")
JOBS_PER_PAGE = 6


class CandidateAccessMixin(PortalAccessMixin):
    portal = "candidate"


class Login(PortalLoginView):
    portal = "candidate"
    template_name = "candidates/login.html"
    form_class = UserLoginForm


class Logout(PortalLogoutView):
    portal = "candidate"


class Register(PortalRegisterView):
    portal = "candidate"
    template_name = "candidates/register.html"
    form_class = UserRegistrationForm


class Dashboard(CandidateAccessMixin, View):
    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        candidate = req.user.candidate
        counts = Application.objects.filter(candidate=candidate).aggregate(
            total=Count("id"),
            accepted=Count("id", filter=Q(status=Application.Status.ACCEPTED)),
            rejected=Count("id", filter=Q(status=Application.Status.REJECTED)),
            in_progress=Count(
                "id",
                filter=Q(
                    status__in=[
                        Application.Status.PENDING,
                        Application.Status.IN_REVIEW,
                        Application.Status.SHORTLISTED,
                    ]
                ),
            ),
        )
        return render(
            req,
            "candidates/dashboard.html",
            {
                "total": counts["total"],
                "accepted": counts["accepted"],
                "rejected": counts["rejected"],
                "in_progress": counts["in_progress"],
                "saved_count": SavedPosting.objects.filter(candidate=candidate).count(),
                "alert_count": JobAlert.objects.filter(
                    candidate=candidate, is_active=True
                ).count(),
                "completeness": candidate.profile_completeness,
            },
        )


def _order(postings, sort: str):
    if sort == JobFilterForm.SORT_SALARY:
        return postings.order_by(
            F("salary_max").desc(nulls_last=True),
            F("salary_min").desc(nulls_last=True),
            "-created_at",
        )
    if sort == JobFilterForm.SORT_DEADLINE:
        return postings.order_by(F("deadline").asc(nulls_last=True), "-created_at")
    return postings.order_by("-created_at", "-id")


class Postings(CandidateAccessMixin, View):
    """Browse open postings (with filters) and see one posting in detail."""

    def get(self, req: AuthenticatedRequest, pk: int | None = None) -> HttpResponse:
        if pk:
            return self._detail(req, pk)

        candidate = req.user.candidate
        form = JobFilterForm(req.GET or None)
        query = form.cleaned_data["q"] if form.is_valid() else ""
        sort = form.cleaned_data["sort"] if form.is_valid() else ""
        postings = (
            JobPosting.objects.open()
            .search(query, **form.search_kwargs())
            .select_related("employer")
            .prefetch_related("skills")
        )
        page = Paginator(_order(postings, sort), JOBS_PER_PAGE).get_page(
            req.GET.get("page")
        )

        skill_ids = candidate_skill_ids(candidate)
        saved_ids = set(
            SavedPosting.objects.filter(candidate=candidate).values_list(
                "posting_id", flat=True
            )
        )
        for posting in page:
            posting.match = match_score(candidate, posting, skill_ids)
            posting.is_saved = posting.pk in saved_ids

        params = req.GET.copy()
        params.pop("page", None)
        return render(
            req,
            "candidates/jobs.html",
            {"postings": page, "filter_form": form, "query_string": params.urlencode()},
        )

    def _detail(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        candidate = req.user.candidate
        posting = (
            JobPosting.objects.select_related("employer")
            .prefetch_related("skills")
            .filter(pk=pk)
            .first()
        )
        if posting is None:
            messages.error(req, POSTING_NOT_FOUND)
            return redirect("candidate_jobs")

        application = (
            Application.objects.filter(candidate=candidate, posting=posting)
            .prefetch_related("events")
            .first()
        )
        return render(
            req,
            "candidates/job.html",
            {
                "form": ResumeUploadForm(),
                "posting": posting,
                "employer": posting.employer,
                "application": application,
                "is_saved": SavedPosting.objects.filter(
                    candidate=candidate, posting=posting
                ).exists(),
                "match": match_score(candidate, posting),
            },
        )

    def post(self, req: AuthenticatedRequest, pk: int | None = None) -> HttpResponse:
        posting = JobPosting.objects.filter(pk=pk).first() if pk else None
        if posting is None:
            messages.error(req, POSTING_NOT_FOUND)
            return redirect("candidate_jobs")

        job_url = "candidate_job"
        if not posting.is_open:
            messages.error(req, _("This job is no longer accepting applications."))
            return redirect(job_url, pk=posting.pk)

        form = ResumeUploadForm(req.POST, req.FILES)
        if not form.is_valid():
            for errors in form.errors.values():
                for error in errors:
                    messages.error(req, str(error))
            return redirect(job_url, pk=posting.pk)

        candidate = req.user.candidate
        if Application.objects.filter(candidate=candidate, posting=posting).exists():
            messages.error(req, ALREADY_APPLIED)
            return redirect(job_url, pk=posting.pk)

        application = Application(
            candidate=candidate,
            posting=posting,
            resume=form.cleaned_data["resume"],
            cover_letter=form.cleaned_data["cover_letter"],
        )
        try:
            with transaction.atomic():
                application.save()
        except IntegrityError:
            # FileField writes the PDF before the INSERT, so a failed insert
            # (a concurrent duplicate) leaves the file behind: remove it.
            if application.resume.name:
                application.resume.storage.delete(application.resume.name)
            messages.error(req, ALREADY_APPLIED)
            return redirect(job_url, pk=posting.pk)

        try:
            summarize_application.delay(application.id)
        except Exception:
            # The application is saved; only the AI summary is delayed.
            logger.exception(
                "resume_summary_queue_failed", application_id=application.id
            )

        messages.success(req, _("Your application was sent."))
        return redirect(job_url, pk=posting.pk)


class PostingSave(CandidateAccessMixin, View):
    """Toggle the bookmark on a posting."""

    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        posting = JobPosting.objects.filter(pk=pk).first()
        if posting is None:
            messages.error(req, POSTING_NOT_FOUND)
            return redirect("candidate_jobs")

        saved, created = SavedPosting.objects.get_or_create(
            candidate=req.user.candidate, posting=posting
        )
        if created:
            messages.success(req, _("Job saved."))
        else:
            saved.delete()
            messages.success(req, _("Job removed from your saved jobs."))
        # Only our own list pages are valid return targets (never a user-given URL).
        next_name = req.POST.get("next", "")
        if next_name in {"candidate_jobs", "candidate_saved"}:
            return redirect(next_name)
        return redirect("candidate_job", pk=posting.pk)


class SavedPostings(CandidateAccessMixin, View):
    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        saved = (
            SavedPosting.objects.filter(candidate=req.user.candidate)
            .select_related("posting__employer")
            .prefetch_related("posting__skills")
        )
        page = Paginator(saved, 10).get_page(req.GET.get("page"))
        return render(req, "candidates/saved.html", {"saved": page})


class Applications(CandidateAccessMixin, View):
    """The candidate's own applications and their status."""

    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        applications = (
            Application.objects.filter(candidate=req.user.candidate)
            .select_related("posting__employer")
            .order_by("-applied_at")
        )
        page = Paginator(applications, 10).get_page(req.GET.get("page"))
        return render(req, "candidates/applications.html", {"applications": page})


class ApplicationWithdraw(CandidateAccessMixin, View):
    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        application = Application.objects.filter(
            pk=pk, candidate=req.user.candidate
        ).first()
        if application is None:
            messages.error(req, _("This application was not found."))
            return redirect("candidate_applications")

        if not application.can_withdraw:
            messages.error(req, _("This application can no longer be withdrawn."))
        else:
            application.change_status(Application.Status.WITHDRAWN, actor=req.user)
            messages.success(req, _("Your application was withdrawn."))
        return redirect("candidate_job", pk=application.posting_id)


class Settings(CandidateAccessMixin, View):
    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        form = ProfileForm(instance=req.user.candidate)
        return render(req, "candidates/settings.html", {"form": form})

    def post(self, req: AuthenticatedRequest) -> HttpResponse:
        form = ProfileForm(req.POST, instance=req.user.candidate)
        if form.is_valid():
            form.save()
            messages.success(req, _("Your details were saved."))
            return redirect("candidate_settings")

        messages.error(req, _("Nothing was saved. Fix the form errors."))
        return render(req, "candidates/settings.html", {"form": form})


class Alerts(CandidateAccessMixin, View):
    """List the candidate's job alerts and create a new one."""

    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        return self._render(req, JobAlertForm())

    def post(self, req: AuthenticatedRequest) -> HttpResponse:
        form = JobAlertForm(req.POST)
        if form.is_valid():
            alert = form.save(commit=False)
            alert.candidate = req.user.candidate
            alert.save()
            form.save_m2m()
            messages.success(req, _("Job alert created."))
            return redirect("candidate_alerts")

        messages.error(req, _("Nothing was saved. Fix the form errors."))
        return self._render(req, form)

    @staticmethod
    def _render(req: AuthenticatedRequest, form: JobAlertForm) -> HttpResponse:
        alerts = JobAlert.objects.filter(candidate=req.user.candidate).prefetch_related(
            "skills"
        )
        return render(req, "candidates/alerts.html", {"form": form, "alerts": alerts})


class OwnedAlertMixin(CandidateAccessMixin):
    @staticmethod
    def get_alert(req: AuthenticatedRequest, pk: int) -> JobAlert | None:
        return JobAlert.objects.filter(pk=pk, candidate=req.user.candidate).first()


class AlertToggle(OwnedAlertMixin, View):
    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        alert = self.get_alert(req, pk)
        if alert is None:
            messages.error(req, _("This job alert was not found."))
        else:
            alert.is_active = not alert.is_active
            alert.save(update_fields=["is_active", "updated_at"])
            messages.success(
                req,
                _("Job alert switched on.")
                if alert.is_active
                else _("Job alert switched off."),
            )
        return redirect("candidate_alerts")


class AlertDelete(OwnedAlertMixin, View):
    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        alert = self.get_alert(req, pk)
        if alert is None:
            messages.error(req, _("This job alert was not found."))
        else:
            alert.delete()
            messages.success(req, _("Job alert deleted."))
        return redirect("candidate_alerts")


class AlertUnsubscribe(View):
    """Public one-click unsubscribe from an e-mail link (a signed token, no login).

    GET only shows a confirmation page, because mail scanners follow links; the
    alert is switched off by the POST.
    """

    template_name = "candidates/alert_unsubscribe.html"

    def get(self, req, token: str) -> HttpResponse:
        alert = alert_from_token(token)
        return render(
            req,
            self.template_name,
            {"alert": alert, "valid": alert is not None},
            status=200 if alert else 404,
        )

    def post(self, req, token: str) -> HttpResponse:
        alert = alert_from_token(token)
        if alert is None:
            return render(req, self.template_name, {"valid": False}, status=404)

        alert.is_active = False
        alert.save(update_fields=["is_active", "updated_at"])
        return render(
            req, self.template_name, {"alert": alert, "valid": True, "done": True}
        )
