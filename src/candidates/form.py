from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.functional import Promise
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from applications.models import Application
from employers.models import JobPosting, Skill, WorkMode

from .models import Candidate, JobAlert

FORM_CONTROL = {"class": "form-control"}
FORM_SELECT = {"class": "form-select"}


def text_input(placeholder: str | Promise = "") -> forms.TextInput:
    return forms.TextInput(attrs={**FORM_CONTROL, "placeholder": placeholder})


class UserLoginForm(AuthenticationForm):
    username = forms.CharField(label=_("Username"), widget=text_input(_("Username")))
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(
            attrs={**FORM_CONTROL, "placeholder": _("Password")}
        ),
    )


class UserRegistrationForm(UserCreationForm):
    username = forms.CharField(label=_("Username"), widget=text_input(_("Username")))
    first_name = forms.CharField(
        label=_("First name"),
        max_length=30,
        required=True,
        widget=text_input(_("First name")),
    )
    last_name = forms.CharField(
        label=_("Last name"),
        max_length=30,
        required=True,
        widget=text_input(_("Last name")),
    )
    email = forms.EmailField(
        label=_("Email"),
        required=True,
        widget=forms.EmailInput(attrs={**FORM_CONTROL, "placeholder": _("Email")}),
    )
    password1 = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(
            attrs={**FORM_CONTROL, "placeholder": _("Password")}
        ),
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        widget=forms.PasswordInput(
            attrs={**FORM_CONTROL, "placeholder": _("Confirm password")}
        ),
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        ]

    def clean_email(self):
        email = self.cleaned_data["email"]
        if Candidate.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                _(
                    "This email is already registered. Register with another "
                    "email or sign in."
                )
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]

        if commit:
            with transaction.atomic():
                user.save()
                language = get_language() or settings.LANGUAGE_CODE
                Candidate.objects.create(
                    user=user,
                    first_name=self.cleaned_data["first_name"],
                    last_name=self.cleaned_data["last_name"],
                    email=self.cleaned_data["email"],
                    # Alerts and status e-mails start in the registration language.
                    language=language
                    if language in dict(settings.LANGUAGES)
                    else settings.LANGUAGE_CODE,
                )
        return user


class ResumeUploadForm(forms.ModelForm):
    resume = forms.FileField(
        label=_("Resume"),
        widget=forms.ClearableFileInput(
            attrs={**FORM_CONTROL, "placeholder": _("Resume"), "accept": ".pdf"}
        ),
    )
    cover_letter = forms.CharField(
        label=_("Cover letter"),
        required=False,
        widget=forms.Textarea(
            attrs={**FORM_CONTROL, "placeholder": _("Cover letter"), "rows": 4}
        ),
    )

    class Meta:
        model = Application
        fields = ["resume", "cover_letter"]

    def clean_resume(self):
        resume = self.cleaned_data["resume"]

        if resume.size > settings.RESUME_MAX_UPLOAD_BYTES:
            limit_mb = settings.RESUME_MAX_UPLOAD_BYTES // (1024 * 1024)
            raise forms.ValidationError(
                _("The file is larger than %(limit)d MB. Choose a smaller file."),
                params={"limit": limit_mb},
            )

        if not resume.name.lower().endswith(".pdf"):
            raise forms.ValidationError(
                _("Only PDF files are allowed. Save your resume as a PDF.")
            )

        header = resume.read(5)
        resume.seek(0)
        if header != b"%PDF-":
            raise forms.ValidationError(
                _("This file is not a valid PDF. Save it again as a PDF.")
            )

        return resume


class ProfileForm(forms.ModelForm):
    """Everything a candidate can edit about themself."""

    class Meta:
        model = Candidate
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "date_of_birth",
            "headline",
            "city",
            "skills",
            "experience_years",
            "education_level",
            "expected_salary",
            "expected_salary_currency",
            "preferred_work_mode",
            "linkedin_url",
            "is_open_to_work",
            "language",
        ]
        widgets = {
            "first_name": text_input(_("First name")),
            "last_name": text_input(_("Last name")),
            "email": forms.EmailInput(
                attrs={**FORM_CONTROL, "placeholder": _("Email")}
            ),
            "phone_number": text_input("+98 912 000 0000"),
            "date_of_birth": forms.DateInput(
                attrs={**FORM_CONTROL, "type": "date"}, format="%Y-%m-%d"
            ),
            "headline": text_input(_("Headline")),
            "city": text_input(_("City")),
            "skills": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "experience_years": forms.NumberInput(
                attrs={**FORM_CONTROL, "min": 0, "max": 60}
            ),
            "education_level": forms.Select(attrs=FORM_SELECT),
            "expected_salary": forms.NumberInput(attrs={**FORM_CONTROL, "min": 0}),
            "expected_salary_currency": forms.Select(attrs=FORM_SELECT),
            "preferred_work_mode": forms.Select(attrs=FORM_SELECT),
            "linkedin_url": forms.URLInput(
                attrs={**FORM_CONTROL, "placeholder": "https://www.linkedin.com/in/..."}
            ),
            "is_open_to_work": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "language": forms.Select(attrs=FORM_SELECT),
        }

    def clean_email(self):
        email = self.cleaned_data["email"]
        clashes = Candidate.objects.filter(email__iexact=email)
        if self.instance.pk:
            clashes = clashes.exclude(pk=self.instance.pk)
        if clashes.exists():
            raise forms.ValidationError(_("This email is already registered."))
        return email

    def save(self, commit=True):
        candidate = super().save(commit=False)
        if commit:
            # User carries a copy of these fields; keep both rows in step.
            with transaction.atomic():
                candidate.save()
                self.save_m2m()
                user = candidate.user
                user.first_name = candidate.first_name
                user.last_name = candidate.last_name
                user.email = candidate.email
                user.save(update_fields=["first_name", "last_name", "email"])
        return candidate


class JobAlertForm(forms.ModelForm):
    class Meta:
        model = JobAlert
        fields = [
            "name",
            "keywords",
            "location",
            "work_mode",
            "employment_type",
            "min_salary",
            "skills",
            "frequency",
        ]
        widgets = {
            "name": text_input(_("Alert name")),
            "keywords": text_input(_("Keywords")),
            "location": text_input(_("City")),
            "work_mode": forms.Select(attrs=FORM_SELECT),
            "employment_type": forms.Select(attrs=FORM_SELECT),
            "min_salary": forms.NumberInput(attrs={**FORM_CONTROL, "min": 0}),
            "skills": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "frequency": forms.Select(attrs=FORM_SELECT),
        }


class JobFilterForm(forms.Form):
    """GET filters of the candidate's job list. Every field is optional."""

    SORT_NEWEST = "newest"
    SORT_SALARY = "salary"
    SORT_DEADLINE = "deadline"

    q = forms.CharField(
        label=_("Search"), required=False, widget=text_input(_("Search jobs"))
    )
    location = forms.CharField(
        label=_("City"), required=False, widget=text_input(_("City"))
    )
    work_mode = forms.ChoiceField(
        label=_("Work mode"),
        required=False,
        choices=[("", _("Any work mode")), *WorkMode.choices],
        widget=forms.Select(attrs=FORM_SELECT),
    )
    employment_type = forms.ChoiceField(
        label=_("Employment type"),
        required=False,
        choices=[("", _("Any type")), *JobPosting.EmploymentType.choices],
        widget=forms.Select(attrs=FORM_SELECT),
    )
    seniority = forms.ChoiceField(
        label=_("Seniority"),
        required=False,
        choices=[("", _("Any level")), *JobPosting.Seniority.choices],
        widget=forms.Select(attrs=FORM_SELECT),
    )
    min_salary = forms.IntegerField(
        label=_("Minimum salary"),
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={**FORM_CONTROL, "min": 0}),
    )
    skills = forms.ModelMultipleChoiceField(
        label=_("Skills"),
        required=False,
        queryset=Skill.objects.all(),
        widget=forms.SelectMultiple(attrs={**FORM_SELECT, "size": 4}),
    )
    remote_only = forms.BooleanField(
        label=_("Remote only"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    sort = forms.ChoiceField(
        label=_("Sort by"),
        required=False,
        choices=[
            (SORT_NEWEST, _("Newest first")),
            (SORT_SALARY, _("Highest salary")),
            (SORT_DEADLINE, _("Closing soon")),
        ],
        widget=forms.Select(attrs=FORM_SELECT),
    )

    def search_kwargs(self) -> dict:
        """Arguments for ``JobPostingQuerySet.search`` (none if the form is invalid)."""
        if not self.is_valid():
            return {}
        data = self.cleaned_data
        return {
            "location": data["location"],
            "work_mode": data["work_mode"],
            "employment_type": data["employment_type"],
            "seniority": data["seniority"],
            "min_salary": data["min_salary"],
            "skills": list(data["skills"]),
            "remote_only": data["remote_only"],
        }
