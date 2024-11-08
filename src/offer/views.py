
# python imports
import os
import string
import random

from zipfile import ZipFile, ZIP_DEFLATED

# django imports
from django.views import View

from django.http import HttpResponse
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

        # get number of created jobs
        num_of_created_jobs = Job.objects.filter(offer_id=offer.id).count()

        # get number of job receive
        num_of_resume_receive = JobRequest.objects.filter(
            job_id__offer_id=offer.id).count()

        return render(req, "offer/dashboard.html", {
            "num_of_created_jobs": num_of_created_jobs,
            "num_of_resume_receive": num_of_resume_receive,
        })


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

        user = Offer.objects.get(user=req.user)
        form = OfferUpdateForm(instance=user)
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

        form = OfferUpdateForm(req.POST, instance=req.user)
        if form.is_valid():
            form.save()
            messages.success(req, "اطلاعات با موفقیت به‌روز شد!")
            return redirect("/offer/settings/")

        messages.error(req, "لطفاً اطلاعات را بررسی کنید.")
        return render(req, "offer/settings.html", {"form": form})


class Jobs(LoginRequiredMixin, View):
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

        offer_id = Offer.objects.get(user=req.user)
        jobs = Job.objects.filter(offer_id=offer_id).all()
        form = JobCreateForm(instance=offer_id)
        return render(req, "offer/jobs.html", {
            "form": form,
            "jobs": jobs,
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

        offer_id = Offer.objects.get(user=req.user)
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


class Utility(LoginRequiredMixin, View):
    login_url = '/offer/login/'

    @staticmethod
    def get_file_size_mb(file_path):
        file_size_bytes = os.path.getsize(file_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
        return file_size_mb

    @staticmethod
    def generate_random_string(length):
        characters = string.ascii_letters + string.digits
        random_string = ''.join(random.choice(characters)
                                for _ in range(length))
        return random_string

    def get(self, req: HttpRequest, pk: int = None):
        if not hasattr(req.user, 'offer'):
            logout(req)
            messages.error(
                req,
                "شما دسترسی به این بخش ندارید! لطفا"
                " با اکانت کاربری خود وارد شوید",
            )
            return redirect("/offer/login/")

        try:
            offer_id = Offer.objects.get(user=req.user)
            job_id = Job.objects.get(pk=pk, offer_id=offer_id)
            allResume = JobRequest.objects.filter(job_id=job_id).all()
        except Offer.DoesNotExist:
            messages.error(req, "شغل مورد نظر یافت نشد!")
            return redirect("/offer/jobs/")

        if not allResume:
            messages.error(req, "رزومه‌ای برای این شغل ثبت نشده است!")
            return redirect("/offer/jobs/")

        pathAllResume = [r.path_resume for r in allResume]
        tempFileName = "/tmp/" + self.generate_random_string(16) + ".zip"
        with ZipFile(tempFileName, 'w', ZIP_DEFLATED) as zip_file:
            for file_path in pathAllResume:
                zip_file.write(file_path, os.path.basename(file_path))

        with open(tempFileName, 'rb') as f:
            response = HttpResponse(f.read())
            response['Content-Type'] = 'application/zip'
            response['Content-Disposition'] = \
                'attachment; filename=user_files.zip'
            os.remove(tempFileName)
            return response
