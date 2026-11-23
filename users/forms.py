import re
from datetime import date

from captcha.fields import CaptchaField
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from users.models import CustomUser


class CustomRegisterForm(UserCreationForm):
    photo = forms.ImageField(required=True, label='Фото')
    email = forms.EmailField(required=True, label='Почта')
    phone_number = forms.CharField(max_length=15, required=True, initial='+996', label='Телефон')
    date_bir = forms.DateField(required=True, label='Дата рождения', widget=forms.DateInput(attrs={'type': 'date'}))
    gender = forms.ChoiceField(choices=CustomUser.GENDER, required=True, label='Пол')
    city = forms.CharField(max_length=100, required=True, label='Город')

    class Meta:
        model = CustomUser
        fields = ('username', 'password1', 'password2', 'first_name', 'photo', 'email',
                  'phone_number', 'date_bir', 'gender', 'city')

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number'].replace(' ', '')
        if not re.fullmatch(r'\+996\d{9}', phone):
            raise forms.ValidationError('Номер должен быть в формате +996XXXXXXXXX.')
        return phone

    def clean_date_bir(self):
        born = self.cleaned_data['date_bir']
        if born >= date.today():
            raise forms.ValidationError('Дата рождения должна быть в прошлом.')
        return born

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError('Пользователь с такой почтой уже есть.')
        return email


class CaptchaLoginForm(AuthenticationForm):
    """Форма входа: логин, пароль и капча."""

    captcha = CaptchaField(label='Введите символы с картинки',
                           error_messages={'invalid': 'Неверная капча.'})

    field_order = ['username', 'password', 'captcha']

    def clean(self):
        # Пока капча не решена, пароль не проверяем: иначе бот мог бы перебирать пароли без капчи.
        if 'captcha' in self.errors:
            return self.cleaned_data
        return super().clean()
