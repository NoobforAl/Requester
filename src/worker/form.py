from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Worker


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={'class': 'form-control', 'placeholder': 'Password'}))

    class Meta:
        model = User
        fields = ['username', 'password']


class UserRegistrationForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(
            attrs={'class': 'form-control'}))
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(
            attrs={'class': 'form-control'}))
    email = forms.EmailField(
        required=True, widget=forms.EmailInput(
            attrs={'class': 'form-control'}))

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
    class Meta:
        fields = ['job', 'resume', 'cover_letter', 'status']
        fields = ['job', 'resume']
        widgets = {
            'job': forms.Select(attrs={'class': 'form-control'}),
            'resume': forms.ClearableFileInput(
                attrs={'class': 'form-control'}
            ),
        }
