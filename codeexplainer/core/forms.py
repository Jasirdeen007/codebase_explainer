from __future__ import annotations

from django import forms
from django.contrib.auth.models import User


class SignUpForm(forms.Form):
    name = forms.CharField(max_length=150)
    email = forms.EmailField(max_length=254)
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, max_length=128)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("An account with this gmail already exists.")
        return email

    def save(self) -> User:
        name = self.cleaned_data["name"].strip()
        email = self.cleaned_data["email"].strip().lower()
        password = self.cleaned_data["password"]
        return User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=name,
        )


class LoginForm(forms.Form):
    email = forms.EmailField(max_length=254)
    password = forms.CharField(widget=forms.PasswordInput, max_length=128)
