import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from offer.models import Job
from requester.portal import (
    AuthenticatedRequest,
    PortalAccessMixin,
    PortalLoginView,
    PortalLogoutView,
    PortalRegisterView,
)
from requester_handler.tasks import handel_resume

from .form import (
    ResumeUploadForm,
    UserLoginForm,
    UserRegistrationForm,
    UserUpdateForm,
)
from .models import JobRequest

logger = logging.getLogger(__name__)


class WorkerAccessMixin(PortalAccessMixin):
    portal = "worker"


class Login(PortalLoginView):
    portal = "worker"
    template_name = "worker/login.html"
    form_class = UserLoginForm


class Logout(PortalLogoutView):
    portal = "worker"


class Register(PortalRegisterView):
    portal = "worker"
    template_name = "worker/register.html"
    form_class = UserRegistrationForm


class Dashboard(WorkerAccessMixin, View):
    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        counts = JobRequest.objects.filter(worker=req.user.worker).aggregate(
            total=Count("id"),
            accepted=Count("id", filter=Q(status=JobRequest.Status.ACCEPTED)),
            rejected=Count("id", filter=Q(status=JobRequest.Status.REJECTED)),
            pending=Count("id", filter=Q(status=JobRequest.Status.PENDING)),
        )

        return render(
            req,
            "worker/dashboard.html",
            {
                "num_of_user_send_resume": counts["total"],
                "accepted": counts["accepted"],
                "rejected": counts["rejected"],
                "in_progress": counts["pending"],
            },
        )


class Jobs(WorkerAccessMixin, View):
    def get(self, req: AuthenticatedRequest, pk: int | None = None) -> HttpResponse:
        if pk:
            try:
                job = Job.objects.select_related("offer").get(pk=pk)
            except Job.DoesNotExist:
                messages.error(req, "این آگهی شغلی پیدا نشد. ممکن است حذف شده باشد.")
                return redirect("/worker/jobs/")

            return render(
                req,
                "worker/job.html",
                {
                    "form": ResumeUploadForm(),
                    "job": job,
                    "offer": job.offer,
                },
            )

        search_query = req.GET.get("search", "").strip()
        jobs = (
            Job.objects.filter(
                Q(job_name__icontains=search_query) | Q(detail__icontains=search_query)
            )
            .select_related("offer")
            .prefetch_related("tags")
            .order_by("-created_at")
        )
        page_obj_job = Paginator(jobs, 6).get_page(req.GET.get("page_job"))

        sent_requests = (
            JobRequest.objects.filter(worker=req.user.worker)
            .select_related("job", "job__offer")
            .order_by("-applied_at")
        )
        page_obj_sent = Paginator(sent_requests, 5).get_page(
            req.GET.get("page_user_sended")
        )

        return render(
            req,
            "worker/jobs.html",
            {
                "jobs": page_obj_job,
                "userSendedResume": page_obj_sent,
            },
        )

    def post(self, req: AuthenticatedRequest, pk: int | None = None) -> HttpResponse:
        job = Job.objects.filter(pk=pk).first() if pk else None
        if job is None:
            messages.error(req, "این آگهی شغلی پیدا نشد. ممکن است حذف شده باشد.")
            return redirect("/worker/jobs/")

        job_url = f"/worker/jobs/{pk}/"
        form = ResumeUploadForm(req.POST, req.FILES)
        if not form.is_valid():
            for errors in form.errors.values():
                for error in errors:
                    messages.error(req, str(error))
            return redirect(job_url)

        worker = req.user.worker
        if JobRequest.objects.filter(worker=worker, job=job).exists():
            messages.error(req, "شما قبلاً برای این شغل درخواست داده‌اید.")
            return redirect(job_url)

        job_request = JobRequest(
            worker=worker,
            job=job,
            resume=form.cleaned_data["resume"],
            cover_letter=form.cleaned_data["cover_letter"],
        )
        try:
            with transaction.atomic():
                job_request.save()
        except IntegrityError:
            # FileField writes the PDF before the INSERT, so a failed insert
            # (a concurrent duplicate) leaves the file behind: remove it.
            if job_request.resume.name:
                job_request.resume.storage.delete(job_request.resume.name)
            messages.error(req, "شما قبلاً برای این شغل درخواست داده‌اید.")
            return redirect(job_url)

        try:
            handel_resume.delay(job_request.id)
        except Exception:
            # The application is saved; only the AI summary is delayed.
            logger.exception("Could not queue resume summary for %s", job_request.id)

        messages.success(req, "رزومه شما ارسال شد.")
        return redirect(job_url)


class Settings(WorkerAccessMixin, View):
    def get(self, req: AuthenticatedRequest) -> HttpResponse:
        form = UserUpdateForm(instance=req.user.worker)
        return render(req, "worker/settings.html", {"form": form})

    def post(self, req: AuthenticatedRequest) -> HttpResponse:
        form = UserUpdateForm(req.POST, instance=req.user.worker)
        if form.is_valid():
            form.save()
            messages.success(req, "اطلاعات شما ذخیره شد.")
            return redirect("/worker/settings/")

        messages.error(req, "اطلاعات ذخیره نشد. خطاهای فرم را اصلاح کنید.")
        return render(req, "worker/settings.html", {"form": form})
