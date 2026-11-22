from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page


@cache_page(60 * 60 * 24)
def handler404(req: HttpRequest, exception: Http404) -> HttpResponse:
    return render(req, "assets/404.html", status=404)


def mainPage(req: HttpRequest) -> HttpResponse:
    """Landing page; signed-in users go straight to their own portal."""
    if req.user.is_authenticated:
        if hasattr(req.user, "worker"):
            return redirect("/worker/")
        if hasattr(req.user, "offer"):
            return redirect("/offer/")

    return render(req, "assets/home.html")
