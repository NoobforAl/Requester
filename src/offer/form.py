# django imports
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

# app imports
from .models import Job, Offer


class UserLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="نام کاربری",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام کاربری'
        })
    )
    password = forms.CharField(
        label="رمز عبور",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'رمز عبور'
        })
    )


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label="ایمیل",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'test@example.com'
        })
    )
    username = forms.CharField(
        label="نام کاربری",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام کاربری'
        })
    )
    password1 = forms.CharField(
        label="رمز عبور",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'رمز عبور'
        })
    )

    password2 = forms.CharField(
        label="تأیید رمز عبور",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'تأیید رمز عبور'
        })
    )

    company_name = forms.CharField(
        max_length=30,
        label="نام شرکت",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام شرکت'
        })
    )

    company_email = forms.EmailField(
        required=True,
        label="ایمیل شرکت",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'company@example.com'
        })
    )

    detail = forms.CharField(
        required=False,
        label="جزئیات",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'توضیحات اضافی در مورد شرکت',
            'rows': 3
        })
    )

    class Meta:
        model = User
        fields = [
            'username', 'email', 'password1', 'password2',
            'company_name', 'company_email', 'detail',
        ]

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            Offer.objects.create(
                user=user,
                company_name=self.cleaned_data['company_name'],
                company_email=self.cleaned_data['company_email'],
                detail=self.cleaned_data['detail']
            )
        return user


class OfferUpdateForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ['company_name', 'company_email', 'detail']
        widgets = {
            'company_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'نام شرکت'
            }),
            'company_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'ایمیل شرکت'
            }),
            'detail': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'توضیحات اضافی در مورد شرکت',
                'rows': 3
            }),
        }


class JobCreateForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = ['job_name', 'detail', 'tags']
        widgets = {
            'job_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'نام شغل'
            }),
            'detail': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'توضیحات شغل',
                'rows': 3
            }),
            'tags': forms.CheckboxSelectMultiple(attrs={
                'class': 'form-check-input',
                'placeholder': 'برچسب‌ها'
            }),
        }

    def __init__(self, *args, **kwargs):
        super(JobCreateForm, self).__init__(*args, **kwargs)
        self.fields['tags'].queryset = self.fields['tags'].queryset.order_by(
            'name')
