
# python imports
import os
import hashlib

# Django imports
from django.db import IntegrityError

from django.views import View
from django.http.request import HttpRequest

from django.contrib import messages
from django.shortcuts import render, redirect

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import authenticate, login, logout


# app imports
from .models import Worker, JobRequest
from .form import UserLoginForm, UserUpdateForm
from .form import UserRegistrationForm, ResumeUploadForm

# app imports form offer
from offer.models import Job


class Login(View):
    def get(self, req: HttpRequest):
        if req.user.is_authenticated:
            return redirect("/worker/")

        form = UserLoginForm()
        return render(req, "worker/login.html", {"form": form})

    def post(self, req: HttpRequest):
        if req.user.is_authenticated:
            return redirect("/worker/")

        form = UserLoginForm(request=req, data=req.POST)
        if not form.is_valid():
            messages.error(req, form.non_field_errors())
            return redirect("/worker/login/")

        username = form.cleaned_data.get("username")
        password = form.cleaned_data.get("password")
        user = authenticate(req, username=username, password=password)

        if user is None:
            messages.error(req, "نام کاربری یا رمز عبور اشتباه است!")
            return redirect("/worker/login/")

        if hasattr(user, 'worker'):
            login(req, user)
            return redirect("/worker/")

        messages.error(
            req,
            "شما دسترسی به این بخش ندارید! لطفا با اکانت کاربری خود وارد شوید")
        return redirect("/worker/login/")


class Logout(View):
    def get(self, req: HttpRequest):
        logout(req)
        return redirect("/worker/login/")


class Register(View):
    def get(self, req: HttpRequest):
        if req.user.is_authenticated:
            return redirect("/worker/")

        form = UserRegistrationForm()
        return render(req, "worker/register.html", {"form": form})

    def post(self, req: HttpRequest):
        if req.user.is_authenticated:
            return redirect("/worker/")

        form = UserRegistrationForm(req.POST)
        if form.is_valid():
            form.save()
            messages.success(req, "ثبت نام با موفقیت انجام شد!")
            return redirect("/worker/login/")

        messages.error(req, form.errors)
        return render(req, "worker/register.html", {"form": form})


class Dashboard(LoginRequiredMixin, View):
    login_url = '/worker/login/'

    def get(self, req: HttpRequest):
        if not hasattr(req.user, "worker"):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! "
                "لطفا با اکانت کاربری خود وارد شوید"
            )
            return redirect("/worker/login/")

        worker = Worker.objects.get(user=req.user)
        numOfUserSendResume = JobRequest.objects.filter(worker=worker).count()
        return render(req, "worker/dashboard.html", {
            "numOfUserSendResume": numOfUserSendResume
        })


class Jobs(LoginRequiredMixin, View):
    login_url = '/worker/login/'

    def get(self, req: HttpRequest, pk: int = None):
        if not hasattr(req.user, "worker"):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! "
                "لطفا با اکانت کاربری خود وارد شوید"
            )
            return redirect("/worker/login/")

        if pk:
            job: Job
            try:
                job = Job.objects.get(pk=pk)
            except Job.DoesNotExist:
                messages.error(req, "شغل مورد نظر یافت نشد!")
                return redirect("/worker/jobs/")

            form = ResumeUploadForm()
            return render(req, "worker/job.html", {
                "form": form,
                "job": job,
                "offer": job.offer,
            })

        jobs = Job.objects.all()
        userSendedResume = JobRequest.objects.filter(worker=req.user.worker)
        return render(req, "worker/jobs.html", {
            "jobs": jobs,
            "userSendedResume": userSendedResume,
        })

    def post(self, req: HttpRequest, pk: int = None):
        if not hasattr(req.user, "worker"):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! "
                "لطفا با اکانت کاربری خود وارد شوید"
            )
            return redirect("/worker/login/")

        try:
            job = Job.objects.get(pk=pk)
        except Job.DoesNotExist:
            messages.error(req, "شغل مورد نظر یافت نشد!")
            return redirect("/worker/jobs/")

        form = ResumeUploadForm(req.POST, req.FILES)
        if not form.is_valid():
            messages.error(req, form.errors)
            return redirect(f"/worker/jobs/{pk}")

        uploaded_file = form.cleaned_data.get('resume')
        if uploaded_file.size > 5 * 1024 * 1024:  # 5 MB limit
            messages.error(req, "حجم فایل بیش از حد مجاز است!")
            return redirect(f"/worker/jobs/{pk}")

        if not uploaded_file.name.endswith('.pdf'):
            messages.error(req, "فقط فایل‌های PDF مجاز هستند!")
            return redirect(f"/worker/jobs/{pk}")

        file_hash = f"{pk}__" + hashlib.md5(uploaded_file.read()).hexdigest()
        uploaded_file.seek(0)

        _, file_extension = os.path.splitext(uploaded_file.name)
        hashed_file_name = f'{file_hash}{file_extension}'
        save_path = os.path.join('resumes/', hashed_file_name)

        with open(save_path, 'wb') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        try:
            JobRequest.objects.create(
                worker=req.user.worker,
                job=job,
                resume=save_path,
            )
        except IntegrityError:
            messages.error(
                req, "شما قبلاً درخواست این شغل را ارسال کرده‌اید!")
            return redirect(f"/worker/jobs/{pk}")

        messages.success(req, "رزومه با موفقیت ارسال شد!")
        return redirect(f"/worker/jobs/{pk}")


class Settings(LoginRequiredMixin, View):
    login_url = '/worker/login/'

    def get(self, req: HttpRequest):
        if not hasattr(req.user, "worker"):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! "
                "لطفا با اکانت کاربری خود وارد شوید"
            )
            return redirect("/worker/login/")

        form = UserUpdateForm(instance=req.user)
        return render(req, "worker/settings.html", {"form": form})

    def post(self, req: HttpRequest):
        if not hasattr(req.user, "worker"):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! "
                "لطفا با اکانت کاربری خود وارد شوید"
            )
            return redirect("/worker/login/")

        form = UserUpdateForm(req.POST, instance=req.user)
        if form.is_valid():
            form.save()
            messages.success(req, "اطلاعات با موفقیت ذخیره شد!")
            return redirect("/worker/settings/")

        messages.error(req, form.errors)
        return redirect("/worker/settings/")
