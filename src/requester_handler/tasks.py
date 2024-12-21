# native python imports
import os

# pdf parser
import pdfplumber


# pd writer import
from weasyprint import HTML

# celery imports
from celery import shared_task

# langchain imports
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import HumanMessagePromptTemplate

# django import
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

# app imports
from worker.models import JobRequest
from offer.models import Job


def pdf_to_markdown(pdf_path: str) -> str:
    markdown_lines = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                markdown_lines.append(f"# Page {page.page_number}\n")
                markdown_lines.append(text)
                markdown_lines.append("\n--------------------------------\n")

    return ''.join(markdown_lines)


@shared_task()
def handel_resume(reqJobId: int) -> None:
    try:
        job_req = JobRequest.objects.get(id=reqJobId)
    except JobRequest.DoesNotExist:
        print(f"Get error to get job request! {reqJobId}")
        return

    try:
        resume_content = pdf_to_markdown(job_req.resume.path)
    except Exception as err:
        print(f"get error to read this file {job_req.resume.path}", err)
        return

    model = OllamaLLM(
        base_url=os.getenv("LLAMA_SERVER_URL"),
        model=os.getenv("LLAMA_MODEL"),
    )

    prompt = ChatPromptTemplate(
        input_variables=["resume_content"],
        messages=[
            HumanMessagePromptTemplate.from_template(
                "Please summarize the following resume:\n{resume_content}"
            )
        ],
    )

    chain = prompt | model
    result = chain.invoke({"resume_content": resume_content})

    try:
        job_req.ai_summary = result
        job_req.save()
    except Exception:
        return


@shared_task()
def get_report(jobId: int):
    try:
        job = Job.objects.get(id=jobId)
        offer = job.offer
        allRequestForThisJob = JobRequest.objects.filter(job=job)

        context = {
            'offer': offer,
            'job': job,
            'requests': allRequestForThisJob,
        }

        html_content = render_to_string(
            'offer/reports/report_email_template.html', context)

        pdf = HTML(string=html_content).write_pdf()

        subject = f"گزارش شغل {job.job_name}"
        message = f"فایل گزارش پیوست شده است! {job.job_name}"

        email = EmailMessage(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [offer.company_email],
        )

        email.attach(f"job_report_{job.id}.pdf", pdf, 'application/pdf')
        email.send()

    except Exception as e:
        print(f"Error generating or sending the report: {e}")
        return
