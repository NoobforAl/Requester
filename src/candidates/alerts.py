"""Job-alert digests: pick the new postings for an alert and e-mail them."""

import logging

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .models import JobAlert

logger = logging.getLogger(__name__)

UNSUBSCRIBE_SALT = "candidates.job-alert-unsubscribe"
MAX_POSTINGS_PER_DIGEST = 20


def unsubscribe_token(alert: JobAlert) -> str:
    return signing.dumps({"alert": alert.pk}, salt=UNSUBSCRIBE_SALT)


def alert_from_token(token: str) -> JobAlert | None:
    """The alert a one-click unsubscribe link refers to, or None if it is invalid."""
    try:
        data = signing.loads(token, salt=UNSUBSCRIBE_SALT)
    except signing.BadSignature:
        return None
    return JobAlert.objects.filter(pk=data.get("alert")).first()


def absolute_url(path: str) -> str:
    return f"{settings.SITE_URL}{path}"


def new_postings(alert: JobAlert):
    """Open postings matching ``alert`` created since it last sent (or was made)."""
    since = alert.last_sent_at or alert.created_at
    return (
        alert.matching_postings()
        .filter(created_at__gt=since)
        .select_related("employer")
        .order_by("-created_at")[:MAX_POSTINGS_PER_DIGEST]
    )


def send_digest(alert: JobAlert, postings) -> None:
    """E-mail the postings to the alert's candidate, in the candidate's language."""
    candidate = alert.candidate
    with translation.override(candidate.language):
        count = len(postings)
        subject = ngettext(
            "%(count)d new job for “%(name)s”",
            "%(count)d new jobs for “%(name)s”",
            count,
        ) % {"count": count, "name": alert.name}
        lines = [_("Hello %(name)s,") % {"name": candidate.first_name}, ""]
        for posting in postings:
            url = absolute_url(reverse("candidate_job", args=[posting.pk]))
            where = f" ({posting.location})" if posting.location else ""
            lines.append(f"- {posting.title} · {posting.employer.name}{where}\n  {url}")
        unsubscribe = absolute_url(
            reverse("candidate_alert_unsubscribe", args=[unsubscribe_token(alert)])
        )
        lines += ["", _("Stop this alert: %(url)s") % {"url": unsubscribe}]
        send_mail(
            subject,
            "\n".join(lines),
            settings.DEFAULT_FROM_EMAIL,
            [candidate.email],
        )


def send_alerts(frequency: str) -> int:
    """Send every due digest for ``frequency``; returns how many e-mails went out."""
    sent = 0
    alerts = JobAlert.objects.filter(
        is_active=True, frequency=frequency
    ).select_related("candidate")
    for alert in alerts:
        postings = list(new_postings(alert))
        if not postings:
            continue
        try:
            send_digest(alert, postings)
        except Exception:
            logger.exception("Could not send job alert %s", alert.pk)
            continue
        alert.last_sent_at = timezone.now()
        alert.save(update_fields=["last_sent_at", "updated_at"])
        sent += 1
    return sent
