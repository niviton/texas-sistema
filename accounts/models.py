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


# Aparência escolhida por cada pessoa (Início → Aparência).
TEMA_CLARO = 'claro'
TEMA_ESCURO = 'escuro'
TEMA_AUTO = 'auto'
TEMA_CHOICES = [
    (TEMA_CLARO, 'Claro'),
    (TEMA_ESCURO, 'Escuro'),
    (TEMA_AUTO, 'Automático (segue o celular ou computador)'),
]
# chave: (rótulo, família CSS, parâmetro do Google Fonts ou None para a fonte padrão já carregada)
FONTES = {
    'manrope': ('Manrope (padrão)', "'Manrope', system-ui, sans-serif", None),
    'inter': ('Inter', "'Inter', system-ui, sans-serif", 'Inter:wght@400;500;600;700;800'),
    'roboto': ('Roboto', "'Roboto', system-ui, sans-serif", 'Roboto:wght@400;500;700;900'),
    'open_sans': ('Open Sans', "'Open Sans', system-ui, sans-serif", 'Open+Sans:wght@400;500;600;700;800'),
    'atkinson': ('Atkinson Hyperlegible (leitura fácil)', "'Atkinson Hyperlegible', system-ui, sans-serif", 'Atkinson+Hyperlegible:wght@400;700'),
    'lexend': ('Lexend', "'Lexend', system-ui, sans-serif", 'Lexend:wght@400;500;600;700;800'),
}
FONTE_CHOICES = [(k, v[0]) for k, v in FONTES.items()]


class User(AbstractUser):
    ROLE_ADMIN = 'admin'
    ROLE_PROFESSOR = 'professor'
    ROLE_TECNICO = 'tecnico'
    ROLE_LOGISTICA = 'logistica'
    ROLE_VISTORIADOR = 'vistoriador'  # legado: migrado para Técnico (accounts 0004)
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Administrador'),
        (ROLE_TECNICO, 'Técnico (executor de checklists)'),
        (ROLE_LOGISTICA, 'Logística'),
        (ROLE_PROFESSOR, 'Professor'),
    ]

    username = None
    email = models.EmailField('e-mail', unique=True)
    full_name = models.CharField('nome completo', max_length=150)
    cpf = models.CharField('CPF', max_length=14, blank=True)
    phone = models.CharField('telefone', max_length=15, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_PROFESSOR)
    is_approved = models.BooleanField('acesso aprovado', default=False)
    tema = models.CharField('tema', max_length=10, choices=TEMA_CHOICES, default=TEMA_CLARO)
    fonte = models.CharField('fonte', max_length=20, choices=FONTE_CHOICES, default='manrope')

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
    def pode_checklists(self):
        """Faz checklists (vistoria de veículos e pré-uso de equipamentos)."""
        return self.role in (self.ROLE_ADMIN, self.ROLE_TECNICO, self.ROLE_LOGISTICA)

    @property
    def pode_veiculos(self):
        return self.pode_checklists

    @property
    def ve_todo_historico(self):
        """Administrador e Logística veem o histórico de todos; o Técnico, só o próprio."""
        return self.role in (self.ROLE_ADMIN, self.ROLE_LOGISTICA)

    @property
    def fonte_css(self):
        return FONTES.get(self.fonte, FONTES['manrope'])[1]

    @property
    def fonte_google(self):
        return FONTES.get(self.fonte, FONTES['manrope'])[2]

    @property
    def role_label(self):
        return dict(self.ROLE_CHOICES).get(self.role, self.role)
