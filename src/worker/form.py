from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from .models import JobRequest, Worker


class UserLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="نام کاربری",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "نام کاربری"}
        ),
    )
    password = forms.CharField(
        label="رمز عبور",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "رمز عبور"}
        ),
    )


class UserRegistrationForm(UserCreationForm):
    username = forms.CharField(
        label="نام کاربری",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "نام کاربری"}
        ),
    )

    first_name = forms.CharField(
        label="نام",
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "نام"}),
    )

    last_name = forms.CharField(
        label="نام خانوادگی",
        max_length=30,
        required=True,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "نام خانوادگی"}
        ),
    )

    email = forms.EmailField(
        label="ایمیل",
        required=True,
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "ایمیل"}
        ),
    )

    password1 = forms.CharField(
        label="رمز عبور",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "رمز عبور"}
        ),
    )

    password2 = forms.CharField(
        label="تأیید رمز عبور",
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "تأیید رمز عبور"}
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
        if Worker.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "این ایمیل قبلاً ثبت شده است. با ایمیل دیگری ثبت نام کنید "
                "یا وارد حساب خود شوید."
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]

        if commit:
            with transaction.atomic():
                user.save()
                Worker.objects.create(
                    user=user,
                    first_name=self.cleaned_data["first_name"],
                    last_name=self.cleaned_data["last_name"],
                    email=self.cleaned_data["email"],
                )
        return user


class ResumeUploadForm(forms.ModelForm):
    resume = forms.FileField(
        label="رزومه",
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "placeholder": "رزومه"}
        ),
    )
    cover_letter = forms.CharField(
        label="توضیحات بیشتر",
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control", "placeholder": "توضیحات بیشتر"}
        ),
    )

    class Meta:
        model = JobRequest
        fields = ["resume", "cover_letter"]

    def clean_resume(self):
        resume = self.cleaned_data["resume"]

        if resume.size > settings.RESUME_MAX_UPLOAD_BYTES:
            limit_mb = settings.RESUME_MAX_UPLOAD_BYTES // (1024 * 1024)
            raise forms.ValidationError(
                f"حجم فایل بیش از {limit_mb} مگابایت است. فایل کوچک‌تری انتخاب کنید."
            )

        if not resume.name.lower().endswith(".pdf"):
            raise forms.ValidationError(
                "فقط فایل‌های PDF مجاز هستند. رزومه را به صورت PDF ذخیره کنید."
            )

        header = resume.read(5)
        resume.seek(0)
        if header != b"%PDF-":
            raise forms.ValidationError(
                "این فایل یک PDF معتبر نیست. فایل را دوباره ذخیره کنید."
            )

        return resume


class UserUpdateForm(forms.ModelForm):
    first_name = forms.CharField(
        label="نام",
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "نام"}),
    )

    last_name = forms.CharField(
        label="نام خانوادگی",
        max_length=30,
        required=True,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "نام خانوادگی"}
        ),
    )

    email = forms.EmailField(
        label="ایمیل",
        required=True,
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "ایمیل"}
        ),
    )

    class Meta:
        model = Worker
        fields = ["first_name", "last_name", "email"]
