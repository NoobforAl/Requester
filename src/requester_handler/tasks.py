"""Background jobs: resume summaries (local LLM) and per-job PDF reports."""

import logging
from pathlib import Path

import httpx
import pdfplumber
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

from offer.models import Job
from worker.models import JobRequest

logger = logging.getLogger(__name__)


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


def summarize(resume_content: str) -> str:
    """Ask the configured Ollama model for a summary of the resume."""
    # Imported here so the web process does not load langchain until needed.
    from langchain_core.prompts import ChatPromptTemplate  # noqa: PLC0415
    from langchain_ollama.llms import OllamaLLM  # noqa: PLC0415

    model = OllamaLLM(
        base_url=settings.LLAMA_SERVER_URL,
        model=settings.LLAMA_MODEL,
        client_kwargs={"timeout": settings.LLAMA_TIMEOUT_SECONDS},
    )
    prompt = ChatPromptTemplate.from_messages(
        [("human", "Please summarize the following resume:\n{resume_content}")]
    )
    return (prompt | model).invoke({"resume_content": resume_content})


@shared_task(
    autoretry_for=(ConnectionError, TimeoutError, httpx.TransportError),
    retry_backoff=True,
    max_retries=3,
)
def handel_resume(job_request_id: int) -> None:
    """Summarise an uploaded resume and store the summary on the application."""
    if not settings.LLAMA_SERVER_URL:
        logger.info("LLAMA_SERVER_URL is not set; skipping resume summary.")
        return

    try:
        job_request = JobRequest.objects.get(id=job_request_id)
    except JobRequest.DoesNotExist:
        logger.warning("Job request %s no longer exists.", job_request_id)
        return

    try:
        resume_content = pdf_to_markdown(job_request.resume.path)
    except Exception:
        logger.exception("Could not read resume of job request %s", job_request_id)
        return

    job_request.ai_summary = summarize(resume_content)
    job_request.save(update_fields=["ai_summary", "updated_at"])


@shared_task(
    autoretry_for=(OSError,),
    retry_backoff=True,
    max_retries=3,
)
def get_report(job_id: int) -> None:
    """Email the employer a PDF listing every application for one job."""
    # WeasyPrint needs native Pango libraries, so load it only when a report is built.
    from weasyprint import HTML  # noqa: PLC0415

    try:
        job = Job.objects.select_related("offer").get(id=job_id)
    except Job.DoesNotExist:
        logger.warning("Job %s no longer exists; no report sent.", job_id)
        return

    offer = job.offer
    context = {
        "offer": offer,
        "job": job,
        "requests": JobRequest.objects.filter(job=job).select_related("worker"),
    }
    html_content = render_to_string("offer/reports/report_email_template.html", context)
    pdf = HTML(string=html_content, base_url=report_base_url()).write_pdf()

    email = EmailMessage(
        subject=f"گزارش شغل {job.job_name}",
        body=f"فایل گزارش پیوست شده است! {job.job_name}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[offer.company_email],
    )
    email.attach(f"job_report_{job.id}.pdf", pdf, "application/pdf")
    email.send()
    logger.info("Report for job %s sent to %s", job.id, offer.company_email)
