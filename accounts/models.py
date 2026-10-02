from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('O e-mail é obrigatório.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', User.ROLE_PROFESSOR)
        extra_fields.setdefault('is_approved', False)
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', User.ROLE_ADMIN)
        extra_fields.setdefault('is_approved', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    ROLE_ADMIN = 'admin'
    ROLE_PROFESSOR = 'professor'
    ROLE_VISTORIADOR = 'vistoriador'
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Administrador'),
        (ROLE_PROFESSOR, 'Professor'),
        (ROLE_VISTORIADOR, 'Vistoriador (mobilização)'),
    ]

    username = None
    email = models.EmailField('e-mail', unique=True)
    full_name = models.CharField('nome completo', max_length=150)
    cpf = models.CharField('CPF', max_length=14, blank=True)
    phone = models.CharField('telefone', max_length=15, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_PROFESSOR)
    is_approved = models.BooleanField('acesso aprovado', default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    objects = UserManager()

    def __str__(self):
        return self.full_name or self.email

    @property
    def first_name_display(self):
        return self.full_name.split(' ')[0] if self.full_name else self.email

    @property
    def initials(self):
        parts = [p for p in self.full_name.split(' ') if p]
        if not parts:
            return self.email[:2].upper()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def is_admin_geral(self):
        return self.role == self.ROLE_ADMIN

    @property
    def pode_veiculos(self):
        """Acesso ao módulo de veículos: administradores e vistoriadores."""
        return self.role in (self.ROLE_ADMIN, self.ROLE_VISTORIADOR)

    @property
    def role_label(self):
        return dict(self.ROLE_CHOICES).get(self.role, self.role)
