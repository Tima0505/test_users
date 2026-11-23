from django.contrib.auth.models import User
from django.db import models


class CustomUser(User):
    """Пользователь с дополнительными полями профиля (как в примере test_users)."""

    GENDER = (
        ('MALE', 'MALE'),
        ('FEMALE', 'FEMALE'),
    )

    photo = models.ImageField(upload_to='users/')
    phone_number = models.CharField(max_length=15)
    date_bir = models.DateField()
    gender = models.CharField(max_length=100, choices=GENDER)
    city = models.CharField(max_length=100)

    def __str__(self):
        return self.username
