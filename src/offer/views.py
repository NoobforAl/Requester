
# python imports
import os
from datetime import timedelta

# other import pkgs
import jdatetime

# django imports
from django.views import View

from django.db.models import Q
from django.db.models import Count

from django.core.paginator import Paginator

from django.http import FileResponse
from django.http.request import HttpRequest

from django.shortcuts import render, redirect

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin

# app imports
from .models import Offer, Job
from .form import (
    UserRegistrationForm,
    UserLoginForm,
    OfferUpdateForm,
    JobCreateForm,
)

# app imports from worker
from worker.models import JobRequest

# app import form celery
from requester_handler.tasks import get_report


class Login(View):
    def get(self, req: HttpRequest):
        if req.user.is_authenticated:
            return redirect("/offer/")

        form = UserLoginForm()
        return render(req, "offer/login.html", {"form": form})

    def post(self, req: HttpRequest):
        if req.user.is_authenticated:
            return redirect("/offer/")

        form = UserLoginForm(request=req, data=req.POST)
        if not form.is_valid():
            messages.error(req, form.non_field_errors())
            return redirect("/offer/login/")

        username = form.cleaned_data.get("username")
        password = form.cleaned_data.get("password")
        user = authenticate(req, username=username, password=password)

        if user is None:
            messages.error(req, "نام کاربری یا رمز عبور اشتباه است!")
            return redirect("/offer/login/")

        if hasattr(user, 'offer'):
            login(req, user)
            return redirect("/offer/")

        messages.error(
            req,
            "شما دسترسی به این بخش ندارید! لطفا با اکانت کاربری خود وارد شوید")
        return redirect("/offer/login/")


class Logout(LoginRequiredMixin, View):
    login_url = '/offer/login/'

    def get(self, req: HttpRequest):
        logout(req)
        return redirect("/offer/login/")


class Register(View):
    def get(self, req: HttpRequest):
        if req.user.is_authenticated:
            return redirect("/offer/")

        form = UserRegistrationForm()
        return render(req, "offer/register.html", {"form": form})

    def post(self, req: HttpRequest):
        if req.user.is_authenticated:
            return redirect("/offer/")

        form = UserRegistrationForm(req.POST)
        if form.is_valid():
            form.save()
            messages.success(req, "ثبت نام با موفقیت انجام شد!")
            return redirect("/offer/login/")

        messages.error(req, form.errors)
        return render(req, "offer/register.html", {"form": form})


class Dashboard(LoginRequiredMixin, View):
    login_url = '/offer/login/'

    def get(self, req: HttpRequest):
        if not hasattr(req.user, 'offer'):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! لطفا"
                " با اکانت کاربری خود وارد شوید",
            )
            return redirect("/offer/login/")

        offer = Offer.objects.get(user=req.user)

        num_of_created_jobs = Job.objects.filter(offer_id=offer.id).count()
        num_of_resume_receive = JobRequest.objects.filter(
            job_id__offer_id=offer.id).count()

        today = jdatetime.date.today()
        current_month_start = today.replace(day=1)
        last_month_start = (current_month_start -
                            timedelta(days=1)).replace(day=1)
        last_month_end = current_month_start - timedelta(days=1)

        current_month_start_greg = current_month_start.togregorian()
        last_month_start_greg = last_month_start.togregorian()
        last_month_end_greg = last_month_end.togregorian()

        jobs_current_month = Job.objects.filter(
            offer_id=offer.id,
            created_at__gte=current_month_start_greg
        ).count()

        jobs_last_month = Job.objects.filter(
            offer_id=offer.id,
            created_at__range=(last_month_start_greg, last_month_end_greg)
        ).count()

        requests_per_day = JobRequest.objects.filter(
            job_id__offer_id=offer.id,
            applied_at__gte=current_month_start_greg
        ).extra({
            'day': "DATE(applied_at)"
        }).values('day').annotate(count=Count('id')).order_by('day')

        requests_per_day_jalali = [
            {
                'day': jdatetime.date.
                fromgregorian(date=item['day']).strftime('%Y-%m-%d'),
                'count': item['count']
            }
            for item in requests_per_day
        ]

        context = {
            "num_of_created_jobs": num_of_created_jobs,
            "num_of_resume_receive": num_of_resume_receive,
            "jobs_current_month": jobs_current_month,
            "jobs_last_month": jobs_last_month,
            "requests_per_day": requests_per_day_jalali,
        }

        return render(req, "offer/dashboard.html", context)


class Settings(LoginRequiredMixin, View):
    login_url = '/offer/login/'

    def get(self, req: HttpRequest):
        if not hasattr(req.user, 'offer'):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! لطفا"
                " با اکانت کاربری خود وارد شوید",
            )
            return redirect("/offer/login/")

        form = OfferUpdateForm(instance=req.user.offer)
        return render(req, "offer/settings.html", {
            "form": form,
        })

    def post(self, req: HttpRequest):
        if not hasattr(req.user, 'offer'):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! لطفا"
                " با اکانت کاربری خود وارد شوید",
            )
            return redirect("/offer/login/")

        form = OfferUpdateForm(req.POST)
        if form.is_valid():
            form.save()
            messages.success(req, "اطلاعات با موفقیت به‌روز شد!")
            return redirect("/offer/settings/")

        messages.error(req, "لطفاً اطلاعات را بررسی کنید.")
        return render(req, "offer/settings.html", {"form": form})


class Jobs(LoginRequiredMixin, View):
    login_url = '/offer/login/'

    def get(self, req: HttpRequest, pk: int = None):
        if not hasattr(req.user, 'offer'):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! لطفا"
                " با اکانت کاربری خود وارد شوید",
            )
            return redirect("/offer/login/")

        offer_id = Offer.objects.get(user=req.user)
        form = JobCreateForm(instance=offer_id)

        if pk:
            try:
                job = Job.objects.get(id=pk)
            except Job.DoesNotExist:
                print("JobRequest.DoesNotExist")
                messages.error(req, "آگهی شغلی یافت نشد!")
                return redirect("/offer/jobs/")

            if req.GET.get("report", "").lower() == "true":
                get_report.delay(pk)
                messages.warning(
                    req,
                    "درخواست گزارش دریافت شد و بعد "
                    "از 1 الا 3 سه روز کار برای شما ارسال خواهد شد!"
                )
                return redirect("/offer/jobs/")

            search_query = req.GET.get("search", "")
            requests = JobRequest.objects.filter(
                job_id=job.id).order_by("applied_at")

            if search_query:
                requests = requests.filter(
                    Q(worker__first_name__icontains=search_query) |
                    Q(worker__last_name__icontains=search_query) |
                    Q(worker__email__icontains=search_query)
                )

            paginator = Paginator(requests, 10)
            page_number = req.GET.get("page")
            page_obj = paginator.get_page(page_number)

            return render(req, "offer/job.html", {
                "form": form,
                "job": job,
                "listUserJobRequested": page_obj,
                "search_query": search_query,
            })

        requests = Job.objects.filter(offer_id=offer_id).order_by("created_at")
        paginator = Paginator(requests, 10)
        page_number = req.GET.get("page")
        page_obj = paginator.get_page(page_number)

        return render(req, "offer/jobs.html", {
            "form": form,
            "jobs": page_obj,
        })

    def post(self, req: HttpRequest, pk: int = None):
        if not hasattr(req.user, 'offer'):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! لطفا"
                " با اکانت کاربری خود وارد شوید",
            )
            return redirect("/offer/login/")

        offer_id = Offer.objects.get(user=req.user)

        if pk:
            try:
                job = Job.objects.get(id=pk)
            except Job.DoesNotExist:
                messages.error(req, "آگهی شغلی یافت نشد!")
                return redirect("/offer/jobs/")

            form = JobCreateForm(req.POST, instance=job)
            if req.GET.get("edit", "").lower() == "true":
                if form.is_valid():
                    form.save()
                    messages.success(
                        req, "اطلاعات شغل با موفقیت به‌روزرسانی شد!"
                    )
                    return redirect(f"/offer/jobs/{pk}/")

                messages.error(req, "لطفاً اطلاعات را بررسی کنید.")
                jobs = Job.objects.filter(offer_id=offer_id).all()
                return redirect(f"/offer/jobs/{pk}/")

            job.delete()
            messages.success(req, "آگهی شغلی با موفقیت حذف شد!")
            return redirect("/offer/jobs/")

        form = JobCreateForm(req.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.offer_id = offer_id.id
            job.save()
            form.save_m2m()
            messages.success(req, "آگهی شغلی با موفقیت ثبت شد!")
            return redirect("/offer/jobs/")

        messages.error(req, "لطفاً اطلاعات را بررسی کنید.")
        jobs = Job.objects.filter(offer_id=offer_id).all()
        return render(req, "offer/jobs.html", {
            "jobs": jobs,
            "form": form
        })


class Resume(LoginRequiredMixin, View):
    login_url = '/offer/login/'

    def get(self, req: HttpRequest, pk: int):
        if not hasattr(req.user, 'offer'):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! لطفا"
                " با اکانت کاربری خود وارد شوید",
            )
            return redirect("/offer/login/")

        try:
            job = JobRequest.objects.get(id=pk)
        except JobRequest.DoesNotExist:
            messages.error(req, "آگهی شغلی یافت نشد!")
            return redirect("/offer/jobs/")

        if not os.path.exists(job.resume.path):
            messages.error(req, "رزومه یافت نشد!")
            return redirect(f"/offer/jobs/{job.job.id}/")

        try:
            return FileResponse(
                open(job.resume.path, 'rb'),
                content_type='application/pdf'
            )
        except Exception:
            messages.error(req, "خطا در دانلود رزومه!")
            return redirect(f"/offer/jobs/{job.job.id}/")


class ResumeStatus(LoginRequiredMixin, View):
    login_url = '/offer/login/'

    def post(self, req: HttpRequest, pk: int):
        if not hasattr(req.user, 'offer'):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! لطفا"
                " با اکانت کاربری خود وارد شوید",
            )
            return redirect("/offer/login/")

        try:
            job = JobRequest.objects.get(id=pk)
        except JobRequest.DoesNotExist:
            messages.error(req, "آگهی شغلی یافت نشد!")
            return redirect("/offer/jobs/")

        job.status = req.POST.get("status")
        job.save()
        messages.success(req, "وضعیت رزومه با موفقیت تغییر یافت!")
        return redirect(f"/offer/jobs/{job.job.id}/")
