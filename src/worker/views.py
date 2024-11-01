from django.utils.decorators import method_decorator
from django.shortcuts import render, redirect
from django.contrib import messages

from django.http.request import HttpRequest
from django.views import View

from offer.models import job

from hashlib import sha256, md5

from .models import Worker, request_job
from .midelver import login_required
from .forms import FileUploadForm

import os


class Register(View):
    # TODO: notification with email
    # better auth method ?
    def get(self, req: HttpRequest):
        user_auth = req.session.get("Auth-worker", None)
        if user_auth:
            return redirect("/worker/")

        return render(req, "registerWorker.html", {
            "actionForm": "/worker/register/",
            "pageName": "Register",
            "redierctPath": "/worker/login/",
            "redierctName": "Login",
        })

    def post(self, req: HttpRequest):
        # TODO add form model for login or
        email = req.POST["email"]

        try:
            Worker.objects.get(email=email)
            messages.error(req, "A user with this email already exists.")
            return redirect("/worker/register/")
        except Worker.DoesNotExist:
            newWorker = Worker.objects.create(
                first_name=req.POST["first_name"],
                last_name=req.POST["last_name"],
                email=email,
                password=sha256(req.POST["password"].encode()).hexdigest(),
            )
            newWorker.save()
            messages.success(req, "Registration successful!")
            return redirect("/worker/login/")


class Login(View):
    def get(self, req: HttpRequest):
        user_auth = req.session.get("Auth-worker", None)
        if user_auth:
            return redirect("/worker/")

        return render(req, "login.html", {
            "actionForm": "/worker/login/",
            "pageName": "Login",
            "redierctPath": "/worker/register/",
            "redierctName": "Register",
        })

    def post(self, req: HttpRequest):
        email = req.POST["email"]
        password = req.POST["password"]

        try:
            worker = Worker.objects.get(
                email=email, password=sha256(password.encode()).hexdigest())
            req.session["Auth-worker"] = f"{worker.pk}"
            return redirect("/worker/")
        except Worker.DoesNotExist:
            messages.error(req, "User not found!")
            return redirect("/worker/login/")


class Logout(View):
    def get(self, req: HttpRequest):
        del req.session["Auth-worker"]
        return redirect("/worker/login/")


class Dashbord(View):
    @method_decorator(login_required())
    def get(self, req: HttpRequest):
        pk = int(req.session["Auth-worker"])
        worker_id = Worker.objects.get(pk=pk)
        numOfResume = request_job.objects.filter(worker_id=worker_id).count()
        return render(req, "dashbordWorker.html", {
            "home": "/worker/",
            "jobs": "/worker/jobs/",
            "setting": "/worker/info/",
            "logout": "/worker/logout/",
            "numOfResume": numOfResume,
        })


class Jobs(View):
    @method_decorator(login_required())
    def get(self, req: HttpRequest, pk: int = None):
        if pk:
            work: job = None
            try:
                work = job.objects.get(pk=pk)
            except job.DoesNotExist:
                messages.error(req, "Job not exist!")
                return redirect("/worker/jobs/")

            form = FileUploadForm()
            return render(req, "jobworker.html", {
                "home": "/worker/",
                "jobs": "/worker/jobs/",
                "setting": "/worker/info/",
                "logout": "/worker/logout/",
                "job": work,
                "form": form,
                "workerid": work.offer_id.pk,
            })

        else:
            jobs = job.objects.all()
            return render(req, "jobsworker.html", {
                "home": "/worker/",
                "jobs": "/worker/jobs/",
                "setting": "/worker/info/",
                "logout": "/worker/logout/",
                "jobs": jobs,
            })

    @method_decorator(login_required())
    def post(self, req: HttpRequest, pk: int = None):
        work: job = None
        try:
            work = job.objects.get(pk=pk)
        except job.DoesNotExist:
            messages.error(req, "Job not exist!")
            return redirect("/worker/jobs/")

        form = FileUploadForm(req.POST, req.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data['file']
            file_hash = f"{pk}__" + md5(uploaded_file.read()).hexdigest()

            uploaded_file.seek(0)

            _, file_extension = os.path.splitext(uploaded_file.name)
            hashed_file_name = f'{file_hash}{file_extension}'
            save_path = os.path.join('./resumefiles/', hashed_file_name)

            with open(save_path, 'wb') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            try:
                worker_id = int(req.session["Auth-worker"])
                worker = Worker.objects.get(pk=worker_id)
                request_job.objects.create(
                    worker_id=worker,
                    job_id=work,
                    path_resume=save_path,
                )
            except:
                messages.error(req, "you send request for this job!")
                return redirect(f"/worker/jobs/{pk}")

            messages.success(req, "Sended resume!")
            return redirect(f"/worker/jobs/{pk}")

        messages.error(req, "form not valid!")
        return redirect("/worker/jobs/")


class Info(View):
    @method_decorator(login_required())
    def get(self, req: HttpRequest):
        worker_id = int(req.session["Auth-worker"])
        worker = Worker.objects.get(pk=worker_id)
        return render(req, "infoWoker.html", {
            "home": "/worker/",
            "jobs": "/worker/jobs/",
            "setting": "/worker/info/",
            "logout": "/worker/logout/",
            "email": worker.email,
            "first_name": worker.first_name,
            "last_name": worker.last_name,
        })

    @method_decorator(login_required())
    def post(self, req: HttpRequest):
        worker_id = int(req.session["Auth-worker"])
        worker = Worker.objects.get(pk=worker_id)

        if worker.password != sha256(req.POST["password"].encode()).hexdigest():
            messages.error(req, "password not corect!")
            return redirect("/worker/info/")

        Worker.objects.filter(pk=worker_id).update(
            email=req.POST["email"],
            first_name=req.POST["first_name"],
            last_name=req.POST["last_name"],
        )

        messages.success(req, "info changed!")
        return redirect("/worker/info/")
