from django.shortcuts import render, redirect
from django.views.decorators.cache import cache_page
from django.http import HttpResponse, HttpRequest, Http404


@cache_page(60 * 60 * 24)
def handler404(req: HttpRequest, exception: Http404) -> HttpResponse:
    return render(req, "assets/404.html")


@cache_page(60 * 60 * 24)
def mainPage(req: HttpRequest) -> HttpResponse:
    if req.user.is_authenticated:

        if getattr(req.user, "worker", False):
            return redirect("/worker/")

        if getattr(req.user, "offer", False):
            return redirect("/offer/")

    return render(req, "assets/home.html")
