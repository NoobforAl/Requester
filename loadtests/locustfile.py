# ruff: noqa: S311  (random only picks load test inputs, not secrets)
"""Locust load test scenarios for Requester (server-rendered Django views).

NEVER run this against production. The production guard below refuses any host
that is not localhost / 127.0.0.1 / ::1 / a host containing "staging", unless
``LOADTEST_ALLOW_HOST`` names that exact host.

Users:
* ``CandidateUser`` (weight 3): sign in, browse and search jobs, open a job,
  toggle "save job", open saved jobs and applications.
* ``EmployerUser`` (weight 1): sign in, dashboard, own jobs list, job detail,
  and a rare write flow (create a posting, then delete it again).
* ``AnonymousUser`` (weight 1): home page and the login pages.

Environment variables (no credentials live in this file):
* ``LOADTEST_CANDIDATE_USERNAME`` / ``LOADTEST_CANDIDATE_PASSWORD``
* ``LOADTEST_EMPLOYER_USERNAME`` / ``LOADTEST_EMPLOYER_PASSWORD``
* ``LOADTEST_ALLOW_HOST``: exact host name allowed besides the defaults.
* ``LOADTEST_READ_ONLY=1``: skip every task that writes (save toggle, create posting).

Every request carries ``X-Request-ID: loadtest-<uuid>``, so the run can be found
in Loki with ``| json | request_id=~"loadtest-.*"``.
"""

from __future__ import annotations

import logging
import os
import random
import re
import uuid
from urllib.parse import urlsplit

from locust import HttpUser, between, events, task
from locust.exception import StopUser

logger = logging.getLogger("loadtest")

# ----------------------------------------------------------------- production guard

SAFE_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def _hostname(url: str | None) -> str:
    if not url:
        return ""
    return (urlsplit(url).hostname or "").lower()


def host_refusal(url: str | None) -> str | None:
    """Return why ``url`` must not be load tested, or None when it is allowed."""
    if not url:
        return "no target host given (pass --host, e.g. http://127.0.0.1:8181)"
    hostname = _hostname(url)
    if not hostname:
        return f"cannot parse a host name from {url!r}"
    allowed_exact = os.environ.get("LOADTEST_ALLOW_HOST", "").strip().lower()
    if hostname in SAFE_HOSTNAMES or "staging" in hostname:
        return None
    if allowed_exact and hostname == allowed_exact:
        return None
    return (
        f"refusing to load test {hostname!r}: only localhost, 127.0.0.1, ::1 or a "
        "host containing 'staging' are allowed. Set LOADTEST_ALLOW_HOST to the exact "
        "host name to override. NEVER point this at production."
    )


def _refuse(environment, reason: str) -> None:
    logger.error("LOAD TEST REFUSED: %s", reason)
    environment.process_exit_code = 2
    if environment.runner is not None:
        environment.runner.quit()


@events.init.add_listener
def _guard_on_init(environment, **_kwargs) -> None:
    # --host given on the command line (or in a config file): check it right away.
    # With the web UI and no --host, the host is checked again at test_start.
    if environment.host:
        reason = host_refusal(environment.host)
        if reason:
            _refuse(environment, reason)


@events.test_start.add_listener
def _guard_on_test_start(environment, **_kwargs) -> None:
    reason = host_refusal(environment.host)
    if reason:
        _refuse(environment, reason)


# ----------------------------------------------------------------- helpers

READ_ONLY = os.environ.get("LOADTEST_READ_ONLY", "").lower() in {"1", "true", "yes"}
SEARCH_TERMS = ["python", "django", "developer", "data", "design", "remote", "react"]
CSRF_INPUT_RE = re.compile(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"')


def request_id() -> str:
    return f"loadtest-{uuid.uuid4()}"


class PortalUser(HttpUser):
    """Shared request helpers: request id header, CSRF, login detection."""

    abstract = True
    wait_time = between(1, 3)

    # Set by subclasses; empty portal means "no login" (anonymous).
    portal = ""
    username_env = ""
    password_env = ""

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"X-Request-ID": request_id()}
        if extra:
            headers.update(extra)
        return headers

    @property
    def login_path(self) -> str:
        return f"/{self.portal}s/login/"

    def _check(
        self,
        response,
        expect_path: str | None = None,
        require_redirect: bool = False,
    ) -> None:
        """Mark a response failed on HTTP errors or a bounce to the login page."""
        if response.status_code >= 400:  # noqa: PLR2004
            response.failure(f"HTTP {response.status_code}")
            return
        if require_redirect and not response.history:
            # Django form views redirect on success (PRG) and re-render on errors.
            response.failure("form was rejected (no redirect after POST)")
            return
        final_path = urlsplit(response.url or "").path
        if self.portal and final_path == self.login_path:
            response.failure("redirected to the login page (session lost?)")
            return
        if expect_path and final_path != expect_path:
            response.failure(f"expected to land on {expect_path}, got {final_path}")
            return
        response.success()

    def get(self, path: str, name: str | None = None, **kwargs):
        with self.client.get(
            path, name=name, headers=self._headers(), catch_response=True, **kwargs
        ) as response:
            self._check(response)
            return response

    def csrf_token(self, html: str = "") -> str:
        """CSRF token from the cookie, else from a hidden input in ``html``."""
        token = self.client.cookies.get("csrftoken")
        if token:
            return token
        match = CSRF_INPUT_RE.search(html)
        return match.group(1) if match else ""

    def post(  # noqa: PLR0913
        self,
        path: str,
        data: dict,
        *,
        name: str | None = None,
        referer_path: str | None = None,
        expect_path: str | None = None,
        require_redirect: bool = True,
    ):
        payload = {"csrfmiddlewaretoken": self.csrf_token(), **data}
        referer = f"{self.host.rstrip('/')}{referer_path or path}"
        with self.client.post(
            path,
            data=payload,
            name=name,
            headers=self._headers({"Referer": referer}),
            catch_response=True,
        ) as response:
            self._check(
                response, expect_path=expect_path, require_redirect=require_redirect
            )
            return response

    def on_start(self) -> None:
        # Second line of defence: never send a request to a refused host.
        reason = host_refusal(self.host)
        if reason:
            logger.error("LOAD TEST REFUSED: %s", reason)
            raise StopUser()
        if self.portal:
            self.login()

    def login(self) -> None:
        username = os.environ.get(self.username_env, "")
        password = os.environ.get(self.password_env, "")
        if not username or not password:
            logger.error(
                "%s stopped: set %s and %s to run it.",
                type(self).__name__,
                self.username_env,
                self.password_env,
            )
            raise StopUser()

        with self.client.get(
            self.login_path,
            name=f"{self.login_path} [form]",
            headers=self._headers(),
            catch_response=True,
        ) as form:
            if form.status_code != 200:  # noqa: PLR2004
                form.failure(f"login form HTTP {form.status_code}")
                raise StopUser()
            form.success()
            token = self.csrf_token(form.text)

        dashboard = f"/{self.portal}s/"
        with self.client.post(
            self.login_path,
            data={
                "csrfmiddlewaretoken": token,
                "username": username,
                "password": password,
            },
            name=f"{self.login_path} [submit]",
            headers=self._headers(
                {"Referer": f"{self.host.rstrip('/')}{self.login_path}"}
            ),
            catch_response=True,
        ) as response:
            final_path = urlsplit(response.url or "").path
            if final_path == self.login_path:
                response.failure("login failed: redirected back to the login page")
                logger.error("%s login failed for %r", type(self).__name__, username)
                raise StopUser()
            if response.status_code >= 400 or final_path != dashboard:  # noqa: PLR2004
                response.failure(f"login: HTTP {response.status_code} at {final_path}")
                raise StopUser()
            response.success()


def ids_from(html: str, pattern: re.Pattern[str]) -> list[int]:
    return sorted({int(pk) for pk in pattern.findall(html)})


# ----------------------------------------------------------------- candidate

CANDIDATE_JOB_LINK_RE = re.compile(r'href="/candidates/jobs/(\d+)/"')


class CandidateUser(PortalUser):
    weight = 3
    portal = "candidate"
    username_env = "LOADTEST_CANDIDATE_USERNAME"
    password_env = "LOADTEST_CANDIDATE_PASSWORD"  # noqa: S105 (env var name)

    def on_start(self) -> None:
        self.posting_ids: list[int] = []
        # Number of save toggles per posting; odd counts are undone on stop.
        self.toggles: dict[int, int] = {}
        super().on_start()
        self.jobs_list()

    def on_stop(self) -> None:
        # Put the saved jobs back the way they were before the run.
        for pk, count in self.toggles.items():
            if count % 2:
                self._toggle_save(pk)

    def _pick_posting(self) -> int | None:
        if not self.posting_ids:
            self.jobs_list()
        return random.choice(self.posting_ids) if self.posting_ids else None

    @task(4)
    def jobs_list(self) -> None:
        response = self.get("/candidates/jobs/", name="/candidates/jobs/")
        found = ids_from(response.text or "", CANDIDATE_JOB_LINK_RE)
        if found:
            self.posting_ids = found

    @task(2)
    def jobs_search(self) -> None:
        query = random.choice(SEARCH_TERMS)
        response = self.get(
            f"/candidates/jobs/?q={query}", name="/candidates/jobs/?q=[q]"
        )
        found = ids_from(response.text or "", CANDIDATE_JOB_LINK_RE)
        if found:
            self.posting_ids = sorted(set(self.posting_ids) | set(found))

    @task(3)
    def job_detail(self) -> None:
        pk = self._pick_posting()
        if pk is not None:
            self.get(f"/candidates/jobs/{pk}/", name="/candidates/jobs/[id]/")

    def _toggle_save(self, pk: int) -> None:
        self.post(
            f"/candidates/jobs/{pk}/save/",
            data={"next": "candidate_jobs"},
            name="/candidates/jobs/[id]/save/",
            referer_path="/candidates/jobs/",
            expect_path="/candidates/jobs/",
        )

    @task(1)
    def toggle_save(self) -> None:
        if READ_ONLY:
            return
        pk = self._pick_posting()
        if pk is not None:
            self._toggle_save(pk)
            self.toggles[pk] = self.toggles.get(pk, 0) + 1

    @task(1)
    def saved(self) -> None:
        self.get("/candidates/saved/", name="/candidates/saved/")

    @task(1)
    def applications(self) -> None:
        self.get("/candidates/applications/", name="/candidates/applications/")

    @task(1)
    def dashboard(self) -> None:
        self.get("/candidates/", name="/candidates/")


# ----------------------------------------------------------------- employer

EMPLOYER_JOB_LINK_RE = re.compile(r'href="/employers/jobs/(\d+)/"')


class EmployerUser(PortalUser):
    weight = 1
    portal = "employer"
    username_env = "LOADTEST_EMPLOYER_USERNAME"
    password_env = "LOADTEST_EMPLOYER_PASSWORD"  # noqa: S105 (env var name)

    def on_start(self) -> None:
        self.posting_ids: list[int] = []
        super().on_start()
        self.jobs_list()

    @task(3)
    def dashboard(self) -> None:
        self.get("/employers/", name="/employers/")

    @task(3)
    def jobs_list(self) -> None:
        response = self.get("/employers/jobs/", name="/employers/jobs/")
        found = ids_from(response.text or "", EMPLOYER_JOB_LINK_RE)
        if found:
            self.posting_ids = found

    @task(3)
    def job_detail(self) -> None:
        if not self.posting_ids:
            self.jobs_list()
        if self.posting_ids:
            pk = random.choice(self.posting_ids)
            self.get(f"/employers/jobs/{pk}/", name="/employers/jobs/[id]/")

    @task(1)
    def create_and_delete_posting(self) -> None:
        """Publish a throwaway posting, then delete it so the data stays clean."""
        if READ_ONLY:
            return
        title = f"Loadtest {uuid.uuid4().hex[:12]}"
        response = self.post(
            "/employers/jobs/",
            data={
                "title": title,
                "description": "Temporary posting created by the Locust load test.",
                "location": "",
                "country": "",
                "work_mode": "remote",
                "employment_type": "full_time",
                "seniority": "",
                "salary_min": "",
                "salary_max": "",
                "salary_currency": "USD",
                "deadline": "",
            },
            name="/employers/jobs/ [create]",
            expect_path="/employers/jobs/",
        )
        match = re.search(
            rf'href="/employers/jobs/(\d+)/">{re.escape(title)}<', response.text or ""
        )
        if not match:
            logger.warning("created posting %r not found in the list page", title)
            return
        self.post(
            f"/employers/jobs/{match.group(1)}/delete/",
            data={},
            name="/employers/jobs/[id]/delete/",
            referer_path="/employers/jobs/",
            expect_path="/employers/jobs/",
        )


# ----------------------------------------------------------------- anonymous


class AnonymousUser(PortalUser):
    weight = 1

    @task(3)
    def home(self) -> None:
        self.get("/", name="/")

    @task(1)
    def candidate_login_page(self) -> None:
        self.get("/candidates/login/", name="/candidates/login/")

    @task(1)
    def employer_login_page(self) -> None:
        self.get("/employers/login/", name="/employers/login/")
