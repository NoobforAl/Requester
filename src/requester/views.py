from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render


def handler404(req: HttpRequest, exception: Http404) -> HttpResponse:
    # Not cached: the page shows the visitor's language and flash messages.
    return render(req, "assets/404.html", status=404)


def home(req: HttpRequest) -> HttpResponse:
    """Landing page; signed-in users go straight to their own portal."""
    if req.user.is_authenticated:
        if hasattr(req.user, "candidate"):
            return redirect("candidate_dashboard")
        if hasattr(req.user, "employer"):
            return redirect("employer_dashboard")

    return render(req, "assets/home.html")
