from typing import cast

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from requester.forms import FastRenderMixin

from .models import Employer, JobPosting

FORM_CONTROL = {"class": "form-control"}


def text_input(placeholder: str | Promise = "", **attrs) -> forms.TextInput:
    return forms.TextInput(attrs={**FORM_CONTROL, "placeholder": placeholder, **attrs})


class UserLoginForm(AuthenticationForm):
    username = forms.CharField(label=_("Username"), widget=text_input(_("Username")))
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(
            attrs={**FORM_CONTROL, "placeholder": _("Password")}
        ),
    )


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label=_("Email"),
        widget=forms.EmailInput(
            attrs={**FORM_CONTROL, "placeholder": "test@example.com"}
        ),
    )
    username = forms.CharField(label=_("Username"), widget=text_input(_("Username")))
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
    name = forms.CharField(
        max_length=100, label=_("Company name"), widget=text_input(_("Company name"))
    )
    contact_email = forms.EmailField(
        required=True,
        label=_("Company email"),
        widget=forms.EmailInput(
            attrs={**FORM_CONTROL, "placeholder": "company@example.com"}
        ),
    )
    description = forms.CharField(
        required=False,
        label=_("Description"),
        widget=forms.Textarea(
            attrs={
                **FORM_CONTROL,
                "placeholder": _("Extra information about the company"),
                "rows": 3,
            }
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "email",
            "password1",
            "password2",
            "name",
            "contact_email",
            "description",
        )

    def clean_contact_email(self):
        contact_email = self.cleaned_data["contact_email"]
        if Employer.objects.filter(contact_email__iexact=contact_email).exists():
            raise forms.ValidationError(
                _("This company email is already registered. Enter another one.")
            )
        return contact_email

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            with transaction.atomic():
                user.save()
                Employer.objects.create(
                    user=user,
                    name=self.cleaned_data["name"],
                    contact_email=self.cleaned_data["contact_email"],
                    description=self.cleaned_data["description"],
                )
        return user


class EmployerUpdateForm(forms.ModelForm):
    class Meta:
        model = Employer
        fields = [
            "name",
            "contact_email",
            "description",
            "website",
            "industry",
            "size",
            "city",
            "language",
        ]
        widgets = {
            "name": text_input(_("Company name")),
            "contact_email": forms.EmailInput(
                attrs={**FORM_CONTROL, "placeholder": _("Company email")}
            ),
            "description": forms.Textarea(
                attrs={
                    **FORM_CONTROL,
                    "placeholder": _("Extra information about the company"),
                    "rows": 3,
                }
            ),
            "website": forms.URLInput(
                attrs={**FORM_CONTROL, "placeholder": "https://example.com"}
            ),
            "industry": text_input(_("Industry")),
            "size": forms.Select(attrs={"class": "form-select"}),
            "city": text_input(_("City")),
            "language": forms.Select(attrs={"class": "form-select"}),
        }


class JobPostingForm(FastRenderMixin, forms.ModelForm):
    class Meta:
        model = JobPosting
        fields = [
            "title",
            "description",
            "location",
            "country",
            "work_mode",
            "employment_type",
            "seniority",
            "salary_min",
            "salary_max",
            "salary_currency",
            "deadline",
            "skills",
        ]
        widgets = {
            "title": text_input(_("Job title")),
            "description": forms.Textarea(
                attrs={
                    **FORM_CONTROL,
                    "placeholder": _("Job description"),
                    "rows": 3,
                }
            ),
            "location": text_input(_("City")),
            "country": text_input(_("Country")),
            "work_mode": forms.Select(attrs={"class": "form-select"}),
            "employment_type": forms.Select(attrs={"class": "form-select"}),
            "seniority": forms.Select(attrs={"class": "form-select"}),
            "salary_min": forms.NumberInput(attrs={**FORM_CONTROL, "min": 0}),
            "salary_max": forms.NumberInput(attrs={**FORM_CONTROL, "min": 0}),
            "salary_currency": forms.Select(attrs={"class": "form-select"}),
            "deadline": forms.DateInput(
                attrs={**FORM_CONTROL, "type": "date"}, format="%Y-%m-%d"
            ),
            "skills": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, employer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employer = employer
        skills = cast("forms.ModelMultipleChoiceField", self.fields["skills"])
        if skills.queryset is not None:
            skills.queryset = skills.queryset.order_by("name")

    def clean_title(self):
        """Enforce unique (title, employer); `employer` is not a form field."""
        title = self.cleaned_data["title"]
        if self.employer is not None:
            clashes = JobPosting.objects.filter(employer=self.employer, title=title)
            if self.instance.pk:
                clashes = clashes.exclude(pk=self.instance.pk)
            if clashes.exists():
                raise forms.ValidationError(
                    _("You already have a posting with this title. Choose another.")
                )
        return title

    def clean(self):
        cleaned = super().clean() or {}
        low, high = cleaned.get("salary_min"), cleaned.get("salary_max")
        if low is not None and high is not None and low > high:
            self.add_error(
                "salary_max",
                _("The maximum salary cannot be lower than the minimum."),
            )
        return cleaned
