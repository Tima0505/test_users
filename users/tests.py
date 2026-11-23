"""Тесты регистрации, авторизации с капчей и личного кабинета.

Запуск: python manage.py test -v 2
После запуска результаты сохраняются в reports/test_report.docx (см. users/report_runner.py).
"""
import tempfile
from datetime import date, timedelta

from captcha.models import CaptchaStore
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from users.models import CustomUser

GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
PASSWORD = 'StrongPassword123'


def photo(name='photo.gif'):
    return SimpleUploadedFile(name, GIF, content_type='image/gif')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class BaseUserTest(TestCase):
    """Общие данные: один зарегистрированный пользователь и помощники для капчи."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser', password=PASSWORD, email='test@gmail.com', first_name='Тимур',
            phone_number='+996555123456', date_bir='2004-05-05', gender='MALE', city='Bishkek',
            photo=photo('user.gif'),
        )

    @staticmethod
    def new_captcha():
        """Создаёт капчу и возвращает (ключ, правильный ответ)."""
        key = CaptchaStore.generate_key()
        return key, CaptchaStore.objects.get(hashkey=key).response

    def login_data(self, username='testuser', password=PASSWORD, answer=None, key=None):
        if key is None:
            key, right = self.new_captcha()
            answer = right if answer is None else answer
        return {'username': username, 'password': password, 'captcha_0': key, 'captcha_1': answer}

    def is_logged_in(self):
        return '_auth_user_id' in self.client.session


class RegistrationTests(BaseUserTest):
    def registration_data(self, **changes):
        data = {
            'username': 'newuser', 'password1': PASSWORD, 'password2': PASSWORD,
            'first_name': 'Ivan', 'email': 'ivan@gmail.com', 'phone_number': '+996700111222',
            'date_bir': '2003-03-15', 'gender': 'MALE', 'city': 'Tokmok', 'photo': photo('new.gif'),
        }
        data.update(changes)
        return data

    def test_register_page_opens(self):
        """Страница регистрации открывается и содержит все поля формы."""
        response = self.client.get('/register/')
        self.assertEqual(response.status_code, 200)
        for field in ('username', 'password1', 'password2', 'email', 'phone_number', 'date_bir',
                      'gender', 'city', 'photo'):
            self.assertContains(response, f'name="{field}"')

    def test_register_success(self):
        """Регистрация с правильными данными создаёт пользователя и ведёт на страницу входа."""
        response = self.client.post('/register/', self.registration_data())
        self.assertRedirects(response, '/login/')
        user = CustomUser.objects.get(username='newuser')
        self.assertEqual(user.city, 'Tokmok')
        self.assertTrue(user.photo.name.startswith('users/'))

    def test_register_password_is_hashed(self):
        """Пароль сохраняется в базе в виде хеша, а не открытым текстом."""
        self.client.post('/register/', self.registration_data())
        user = CustomUser.objects.get(username='newuser')
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_register_password_mismatch(self):
        """Если пароли не совпадают, пользователь не создаётся."""
        response = self.client.post('/register/', self.registration_data(password2='Other12345pass'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('password2', response.context['form'].errors)
        self.assertFalse(CustomUser.objects.filter(username='newuser').exists())

    def test_register_weak_password(self):
        """Слишком простой пароль (только цифры) отклоняется."""
        response = self.client.post('/register/', self.registration_data(password1='12345678', password2='12345678'))
        self.assertIn('password2', response.context['form'].errors)
        self.assertFalse(CustomUser.objects.filter(username='newuser').exists())

    def test_register_duplicate_username(self):
        """Нельзя зарегистрировать второй аккаунт с уже занятым логином."""
        response = self.client.post('/register/', self.registration_data(username='testuser'))
        self.assertIn('username', response.context['form'].errors)
        self.assertEqual(CustomUser.objects.filter(username='testuser').count(), 1)

    def test_register_duplicate_email(self):
        """Нельзя зарегистрировать второй аккаунт с уже занятой почтой."""
        response = self.client.post('/register/', self.registration_data(email='test@gmail.com'))
        self.assertIn('email', response.context['form'].errors)

    def test_register_without_photo(self):
        """Фото обязательно: без него регистрация не проходит."""
        data = self.registration_data()
        data.pop('photo')
        response = self.client.post('/register/', data)
        self.assertIn('photo', response.context['form'].errors)

    def test_register_bad_phone(self):
        """Телефон не в формате +996XXXXXXXXX отклоняется."""
        response = self.client.post('/register/', self.registration_data(phone_number='0555123'))
        self.assertIn('phone_number', response.context['form'].errors)

    def test_register_future_birth_date(self):
        """Дата рождения в будущем отклоняется."""
        future = (date.today() + timedelta(days=1)).isoformat()
        response = self.client.post('/register/', self.registration_data(date_bir=future))
        self.assertIn('date_bir', response.context['form'].errors)


class LoginTests(BaseUserTest):
    def test_login_page_has_captcha(self):
        """На странице входа есть картинка капчи и поле для ответа."""
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="captcha"')
        self.assertContains(response, 'name="captcha_1"')
        self.assertContains(response, 'name="captcha_0"')

    def test_login_success(self):
        """Верные логин, пароль и капча: вход выполнен, переход в личный кабинет."""
        response = self.client.post('/login/', self.login_data())
        self.assertRedirects(response, '/profile/')
        self.assertTrue(self.is_logged_in())

    def test_login_wrong_password(self):
        """Неверный пароль при верной капче: вход не выполнен."""
        response = self.client.post('/login/', self.login_data(password='WrongPass999'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.is_logged_in())
        self.assertTrue(response.context['form'].non_field_errors())

    def test_login_unknown_user(self):
        """Несуществующий логин при верной капче: вход не выполнен."""
        response = self.client.post('/login/', self.login_data(username='nobody'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.is_logged_in())

    def test_logout(self):
        """Выход (POST) завершает сессию и ведёт на страницу входа."""
        self.client.force_login(self.user)
        response = self.client.post('/logout/')
        self.assertRedirects(response, '/login/')
        self.assertFalse(self.is_logged_in())

    def test_logout_get_not_allowed(self):
        """Выход по GET-ссылке запрещён (405), сессия не закрывается."""
        self.client.force_login(self.user)
        response = self.client.get('/logout/')
        self.assertEqual(response.status_code, 405)
        self.assertTrue(self.is_logged_in())


class CaptchaTests(BaseUserTest):
    def test_captcha_wrong_answer(self):
        """Верные логин и пароль, но неверная капча: вход не выполнен."""
        response = self.client.post('/login/', self.login_data(answer='wrong'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.is_logged_in())
        self.assertIn('captcha', response.context['form'].errors)

    def test_password_not_checked_without_captcha(self):
        """При неверной капче пароль не проверяется, поэтому подобрать пароль без капчи нельзя."""
        from unittest import mock
        with mock.patch('django.contrib.auth.forms.authenticate') as auth:
            response = self.client.post('/login/', self.login_data(answer='wrong'))
        auth.assert_not_called()
        self.assertFalse(response.context['form'].non_field_errors())

    def test_captcha_empty(self):
        """Пустая капча: вход не выполнен, поле капчи обязательно."""
        response = self.client.post('/login/', self.login_data(answer=''))
        self.assertFalse(self.is_logged_in())
        self.assertIn('captcha', response.context['form'].errors)

    def test_captcha_missing_fields(self):
        """Запрос вообще без полей капчи отклоняется."""
        response = self.client.post('/login/', {'username': 'testuser', 'password': PASSWORD})
        self.assertFalse(self.is_logged_in())
        self.assertIn('captcha', response.context['form'].errors)

    def test_captcha_case_insensitive(self):
        """Ответ на капчу принимается в любом регистре букв."""
        key, right = self.new_captcha()
        response = self.client.post('/login/', self.login_data(key=key, answer=right.upper()))
        self.assertRedirects(response, '/profile/')

    def test_captcha_fake_key(self):
        """Выдуманный ключ капчи не принимается."""
        response = self.client.post('/login/', self.login_data(key='0' * 40, answer='abcde'))
        self.assertFalse(self.is_logged_in())
        self.assertIn('captcha', response.context['form'].errors)

    def test_captcha_cannot_be_reused(self):
        """Одну и ту же капчу нельзя использовать дважды."""
        key, right = self.new_captcha()
        self.client.post('/login/', self.login_data(key=key, answer=right))
        self.client.post('/logout/')
        response = self.client.post('/login/', self.login_data(key=key, answer=right))
        self.assertFalse(self.is_logged_in())
        self.assertIn('captcha', response.context['form'].errors)

    def test_captcha_expired(self):
        """Просроченная капча не принимается."""
        key, right = self.new_captcha()
        CaptchaStore.objects.filter(hashkey=key).update(expiration=timezone.now() - timedelta(minutes=1))
        response = self.client.post('/login/', self.login_data(key=key, answer=right))
        self.assertFalse(self.is_logged_in())
        self.assertIn('captcha', response.context['form'].errors)

    def test_new_captcha_after_error(self):
        """После неудачной попытки форма показывает новую капчу."""
        key, _ = self.new_captcha()
        response = self.client.post('/login/', self.login_data(key=key, answer='wrong'))
        self.assertContains(response, 'name="captcha_0"')
        self.assertNotContains(response, f'value="{key}"')

    def test_captcha_image(self):
        """Картинка капчи отдаётся сервером как PNG."""
        key, _ = self.new_captcha()
        response = self.client.get(f'/captcha/image/{key}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')

    def test_captcha_refresh(self):
        """Капчу можно обновить: сервер выдаёт новый ключ и ссылку на картинку."""
        response = self.client.get('/captcha/refresh/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('key', data)
        self.assertIn('image_url', data)


class ProfileTests(BaseUserTest):
    def test_profile_requires_login(self):
        """Гостя из личного кабинета перенаправляет на страницу входа."""
        response = self.client.get('/profile/')
        self.assertRedirects(response, '/login/?next=/profile/')

    def test_profile_shows_user_data(self):
        """В личном кабинете показаны данные пользователя."""
        self.client.force_login(self.user)
        response = self.client.get('/profile/')
        self.assertEqual(response.status_code, 200)
        for value in ('testuser', 'Тимур', 'test@gmail.com', 'Bishkek', '+996555123456', '05.05.2004'):
            self.assertContains(response, value)

    def test_profile_hides_password(self):
        """Хеш пароля в личном кабинете не выводится."""
        self.client.force_login(self.user)
        response = self.client.get('/profile/')
        self.assertNotContains(response, self.user.password)

    def test_profile_only_own_data(self):
        """Пользователь видит только свои данные, а не чужие."""
        other = CustomUser.objects.create_user(
            username='other', password=PASSWORD, email='other@gmail.com', phone_number='+996777000111',
            date_bir='2001-01-01', gender='FEMALE', city='Osh', photo=photo('other.gif'))
        self.client.force_login(other)
        response = self.client.get('/profile/')
        self.assertContains(response, 'other@gmail.com')
        self.assertNotContains(response, 'test@gmail.com')

    def test_full_flow(self):
        """Полный сценарий: регистрация, вход с капчей, личный кабинет, выход."""
        self.client.post('/register/', {
            'username': 'flowuser', 'password1': PASSWORD, 'password2': PASSWORD, 'first_name': 'Aida',
            'email': 'aida@gmail.com', 'phone_number': '+996555000999', 'date_bir': '2002-02-02',
            'gender': 'FEMALE', 'city': 'Karakol', 'photo': photo('aida.gif'),
        })
        response = self.client.post('/login/', self.login_data(username='flowuser'))
        self.assertRedirects(response, '/profile/')
        self.assertContains(self.client.get('/profile/'), 'Karakol')
        self.client.post('/logout/')
        self.assertRedirects(self.client.get('/profile/'), '/login/?next=/profile/')
