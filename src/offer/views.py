import logging
from datetime import date, datetime, time, timedelta

import jdatetime
from django.contrib import messages
from django.core.paginator import Page, Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import FileResponse, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from requester.portal import (
    AuthenticatedRequest,
    PortalAccessMixin,
    PortalLoginView,
    PortalLogoutView,
    PortalRegisterView,
)
from requester_handler.tasks import get_report
from worker.models import JobRequest

from .form import (
    JobCreateForm,
    OfferUpdateForm,
    UserLoginForm,
    UserRegistrationForm,
)
from .models import Job

logger = logging.getLogger(__name__)

JOB_NOT_FOUND = "این آگهی شغلی پیدا نشد. ممکن است حذف شده باشد."
FORM_INVALID = "اطلاعات ذخیره نشد. خطاهای فرم را اصلاح کنید."


def start_of_day(day: date) -> datetime:
    """Midnight at the start of ``day`` in the current time zone."""
    return timezone.make_aware(datetime.combine(day, time.min))


class OfferAccessMixin(PortalAccessMixin):
    """Employer-only views. Every query below is scoped to ``req.user.offer``."""

    portal = "offer"


class Login(PortalLoginView):
    portal = "offer"
    template_name = "offer/login.html"
    form_class = UserLoginForm


class Logout(PortalLogoutView):
    portal = "offer"


class Register(PortalRegisterView):
    portal = "offer"
    template_name = "offer/register.html"
    form_class = UserRegistrationForm


class Dashboard(OfferAccessMixin, View):
    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        offer = req.user.offer
        jobs = Job.objects.filter(offer=offer)
        job_requests = JobRequest.objects.filter(job__offer=offer)

        today = jdatetime.date.fromgregorian(date=timezone.localdate())
        current_month_start = today.replace(day=1)
        last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)

        current_start = start_of_day(current_month_start.togregorian())
        last_start = start_of_day(last_month_start.togregorian())

        requests_per_day = (
            job_requests.filter(applied_at__gte=current_start)
            .annotate(day=TruncDate("applied_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )

        per_day = [
            {
                "day": jdatetime.date.fromgregorian(date=item["day"]).strftime(
                    "%Y-%m-%d"
                ),
                "count": item["count"],
            }
            for item in requests_per_day
        ]

        return render(
            req,
            "offer/dashboard.html",
            {
                "num_of_created_jobs": jobs.count(),
                "num_of_resume_receive": job_requests.count(),
                "jobs_current_month": jobs.filter(
                    created_at__gte=current_start
                ).count(),
                "jobs_last_month": jobs.filter(
                    created_at__gte=last_start, created_at__lt=current_start
                ).count(),
                "requests_per_day": per_day,
                "requests_per_day_max": max(
                    (item["count"] for item in per_day), default=1
                ),
            },
        )


class Settings(OfferAccessMixin, View):
    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        form = OfferUpdateForm(instance=req.user.offer)
        return render(req, "offer/settings.html", {"form": form})

    def post(self, req: AuthenticatedRequest) -> HttpResponse:
        form = OfferUpdateForm(req.POST, instance=req.user.offer)
        if form.is_valid():
            form.save()
            messages.success(req, "اطلاعات شرکت ذخیره شد.")
            return redirect("/offer/settings/")

        messages.error(req, FORM_INVALID)
        return render(req, "offer/settings.html", {"form": form})


class Jobs(OfferAccessMixin, View):
    """List the employer's jobs and create a new one."""

    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        return render(
            req,
            "offer/jobs.html",
            {"form": JobCreateForm(), "jobs": self._page(req, req.GET.get("page"))},
        )

    def post(self, req: AuthenticatedRequest) -> HttpResponse:
        offer = req.user.offer
        form = JobCreateForm(req.POST, offer=offer)
        if form.is_valid():
            job = form.save(commit=False)
            job.offer = offer
            job.save()
            form.save_m2m()
            messages.success(req, "آگهی شغلی ثبت شد.")
            return redirect("offer_jobs")

        messages.error(req, FORM_INVALID)
        return render(
            req, "offer/jobs.html", {"jobs": self._page(req, 1), "form": form}
        )

    @staticmethod
    def _page(req: AuthenticatedRequest, number: int | str | None) -> Page:
        jobs = Job.objects.filter(offer=req.user.offer).prefetch_related("tags")
        return Paginator(jobs.order_by("created_at"), 10).get_page(number)


class OwnedJobMixin(OfferAccessMixin):
    """Looks up a job, but only one that belongs to the signed-in employer."""

    @staticmethod
    def get_job(req: AuthenticatedRequest, pk: int) -> Job | None:
        return Job.objects.filter(pk=pk, offer=req.user.offer).first()


class JobDetail(OwnedJobMixin, View):
    def get(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        job = self.get_job(req, pk)
        if job is None:
            messages.error(req, JOB_NOT_FOUND)
            return redirect("offer_jobs")

        search_query = req.GET.get("search", "").strip()
        applications = (
            JobRequest.objects.filter(job=job)
            .select_related("worker")
            .order_by("applied_at")
        )
        if search_query:
            applications = applications.filter(
                Q(worker__first_name__icontains=search_query)
                | Q(worker__last_name__icontains=search_query)
                | Q(worker__email__icontains=search_query)
            )

        applications_page = Paginator(applications, 10).get_page(req.GET.get("page"))
        return render(
            req,
            "offer/job.html",
            {
                "form": JobCreateForm(instance=job),
                "job": job,
                "listUserJobRequested": applications_page,
                "search_query": search_query,
            },
        )


class JobEdit(OwnedJobMixin, View):
    """POST only: the edit form lives on the job page."""

    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        job = self.get_job(req, pk)
        if job is None:
            messages.error(req, JOB_NOT_FOUND)
            return redirect("offer_jobs")

        form = JobCreateForm(req.POST, instance=job, offer=req.user.offer)
        if form.is_valid():
            form.save()
            messages.success(req, "آگهی شغلی به‌روز شد.")
        else:
            messages.error(req, FORM_INVALID)
        return redirect("offer_job", pk=job.pk)


class JobDelete(OwnedJobMixin, View):
    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        job = self.get_job(req, pk)
        if job is None:
            messages.error(req, JOB_NOT_FOUND)
        else:
            job.delete()
            messages.success(req, "آگهی شغلی حذف شد.")
        return redirect("offer_jobs")


class JobReport(OwnedJobMixin, View):
    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        job = self.get_job(req, pk)
        if job is None:
            messages.error(req, JOB_NOT_FOUND)
            return redirect("offer_jobs")

        get_report.delay(job.pk)
        messages.warning(
            req,
            "درخواست گزارش ثبت شد. گزارش تا حداکثر سه روز کاری "
            "به ایمیل شرکت شما ارسال می‌شود.",
        )
        return redirect("offer_jobs")


class OwnedApplicationMixin(OfferAccessMixin):
    """Looks up an application, but only one for a job of the signed-in employer."""

    def get_application(self, req: AuthenticatedRequest, pk: int) -> JobRequest | None:
        return (
            JobRequest.objects.select_related("job")
            .filter(pk=pk, job__offer=req.user.offer)
            .first()
        )


class Resume(OwnedApplicationMixin, View):
    def get(self, req: AuthenticatedRequest, pk: int) -> HttpResponseBase:
        application = self.get_application(req, pk)
        if application is None:
            messages.error(req, "این درخواست پیدا نشد.")
            return redirect("/offer/jobs/")

        job_url = f"/offer/jobs/{application.job_id}/"
        try:
            return FileResponse(
                application.resume.open("rb"),
                content_type="application/pdf",
                filename=f"resume_{application.pk}.pdf",
            )
        except (FileNotFoundError, ValueError):
            messages.error(
                req, "فایل رزومه پیدا نشد. از کارجو بخواهید دوباره ارسال کند."
            )
            return redirect(job_url)


class ResumeStatus(OwnedApplicationMixin, View):
    def post(self, req: AuthenticatedRequest, pk: int) -> HttpResponse:
        application = self.get_application(req, pk)
        if application is None:
            messages.error(req, "این درخواست پیدا نشد.")
            return redirect("/offer/jobs/")

        status = req.POST.get("status", "")
        if status not in JobRequest.Status.values:
            messages.error(req, "وضعیت انتخاب‌شده معتبر نیست.")
        else:
            application.status = status
            application.save(update_fields=["status", "updated_at"])
            messages.success(req, "وضعیت درخواست تغییر کرد.")
        return redirect(f"/offer/jobs/{application.job_id}/")
