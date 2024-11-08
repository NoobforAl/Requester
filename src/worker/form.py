from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Worker, JobRequest


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
    username = forms.CharField(
        label="نام کاربری",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام کاربری'
        })
    )

    first_name = forms.CharField(
        label="نام",
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام'
        })
    )

    last_name = forms.CharField(
        label="نام خانوادگی",
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام خانوادگی'
        })
    )

    email = forms.EmailField(
        label="ایمیل",
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'ایمیل'
        }
        )
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

    class Meta:
        model = User
        fields = [
            'username',
            'first_name', 'last_name',
            'email',
            'password1', 'password2',
        ]

    def save(self, commit=True):
        user = super(UserRegistrationForm, self).save(commit=False)
        user.email = self.cleaned_data['email']

        if commit:
            user.save()
            Worker.objects.create(
                user=user,
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                email=self.cleaned_data['email']
            )
        return user


class ResumeUploadForm(forms.ModelForm):
    resume = forms.FileField(
        label="رزومه",
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'placeholder': 'رزومه'
        })
    )
    cover_letter = forms.CharField(
        label="توضیحات بیشتر",
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'توضیحات بیشتر'
        })
    )

    class Meta:
        model = JobRequest
        fields = ['resume', 'cover_letter']


class UserUpdateForm(forms.ModelForm):
    first_name = forms.CharField(
        label="نام",
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام'
        })
    )

    last_name = forms.CharField(
        label="نام خانوادگی",
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'نام خانوادگی'
        })
    )

    email = forms.EmailField(
        label="ایمیل",
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'ایمیل'
        })
    )

    class Meta:
        model = Worker
        fields = ['first_name', 'last_name', 'email']
