"""Background jobs: AI resume summaries, posting reports, status e-mails, job alerts."""

from pathlib import Path

import httpx
import pdfplumber
import structlog
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.translation import gettext as _

from candidates.alerts import send_alerts
from employers.models import JobPosting

from . import ai
from .models import Application

logger = structlog.get_logger(__name__)


def report_base_url() -> str:
    """Directory WeasyPrint resolves relative URLs (the Vazirmatn font) against."""
    return Path(settings.STATICFILES_DIRS[0]).resolve().as_uri() + "/"


def pdf_to_markdown(pdf_path: str) -> str:
    """Extract the text of every page of a PDF as simple markdown."""
    markdown_lines: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                markdown_lines.append(f"# Page {page.page_number}\n")
                markdown_lines.append(text)
                markdown_lines.append("\n--------------------------------\n")

    return "".join(markdown_lines)


@shared_task(
    autoretry_for=(
        ConnectionError,
        TimeoutError,
        httpx.TransportError,
        ai.RetryableAIError,
    ),
    retry_backoff=True,
    max_retries=3,
)
def summarize_application(application_id: int) -> None:
    """Summarise an uploaded resume and store the summary on the application."""
    if not ai.active_provider():
        logger.info("resume_summary_skipped", reason="no_ai_provider")
        return

    try:
        application = Application.objects.select_related("posting__employer").get(
            id=application_id
        )
    except Application.DoesNotExist:
        logger.warning("application_not_found", application_id=application_id)
        return

    try:
        resume_content = pdf_to_markdown(application.resume.path)
    except Exception:
        logger.exception("resume_read_failed", application_id=application_id)
        return

    try:
        summary, provider = ai.summarize(
            resume_content, language=application.posting.employer.language
        )
    except ai.RetryableAIError:
        raise
    except ai.AIError:
        logger.exception("resume_summary_failed", application_id=application_id)
        return

    application.ai_summary = summary
    application.ai_provider = provider
    application.save(update_fields=["ai_summary", "ai_provider", "updated_at"])


@shared_task(
    autoretry_for=(OSError,),
    retry_backoff=True,
    max_retries=3,
)
def send_posting_report(posting_id: int) -> None:
    """Email the employer a PDF listing every application for one posting."""
    # WeasyPrint needs native Pango libraries, so load it only when a report is built.
    from weasyprint import HTML  # noqa: PLC0415

    try:
        posting = JobPosting.objects.select_related("employer").get(id=posting_id)
    except JobPosting.DoesNotExist:
        logger.warning("posting_not_found", posting_id=posting_id)
        return

    employer = posting.employer
    with translation.override(employer.language):
        context = {
            "employer": employer,
            "posting": posting,
            "applications": Application.objects.filter(posting=posting)
            .select_related("candidate")
            .order_by("applied_at"),
        }
        html_content = render_to_string(
            "employers/reports/report_email_template.html", context
        )
        subject = _("Report for %(title)s") % {"title": posting.title}
        body = _("The report is attached: %(title)s") % {"title": posting.title}
    pdf = HTML(string=html_content, base_url=report_base_url()).write_pdf()

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[employer.contact_email],
    )
    email.attach(f"posting_report_{posting.id}.pdf", pdf, "application/pdf")
    email.send()
    logger.info(
        "job_report_sent", posting_id=posting.id, contact_email=employer.contact_email
    )


@shared_task
def notify_status_change(application_id: int) -> None:
    """Tell the candidate (in their language) that an employer changed their status."""
    try:
        application = Application.objects.select_related(
            "candidate", "posting__employer"
        ).get(id=application_id)
    except Application.DoesNotExist:
        return

    candidate = application.candidate
    with translation.override(candidate.language):
        subject = _("Update on your application: %(title)s") % {
            "title": application.posting.title
        }
        body = _(
            "Hello %(name)s,\n\nYour application to “%(title)s” at %(company)s "
            "is now: %(status)s."
        ) % {
            "name": candidate.first_name,
            "title": application.posting.title,
            "company": application.posting.employer.name,
            "status": Application.Status(application.status).label,
        }
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [candidate.email])


@shared_task
def send_job_alerts(frequency: str) -> int:
    """Send the daily or weekly job-alert digests (see ``CELERY_BEAT_SCHEDULE``)."""
    return send_alerts(frequency)
