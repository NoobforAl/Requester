from django.shortcuts import redirect
from django.http.request import HttpRequest


def login_required():
    # TODO: fix auth mod to jwt token
    def decorator(func):
        def wrapper(req: HttpRequest, *args, **kwargs):
            user_auth = req.session.get("Auth-worker", None)
            if user_auth:
                if req.path.find("lgoin") > 0:
                    return redirect("/worker/")
                return func(req, *args, **kwargs)
            else:
                return redirect("login/")
        return wrapper
    return decorator
