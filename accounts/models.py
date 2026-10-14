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
        extra_fields.setdefault('role', User.ROLE_PENDENTE)
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


class Papel(models.Model):
    """
    Papel de acesso, criado e ajustado pelo administrador (ex.: Técnico, Logística, Professor, Motorista).
    Cada pessoa tem um papel; o papel diz quais partes do Polaris ela usa.
    """
    nome = models.CharField('nome do papel', max_length=60, unique=True)
    descricao = models.CharField('descrição', max_length=200, blank=True)
    administrador = models.BooleanField(
        'administrador (acesso total e Configurações)', default=False,
        help_text='Vê e faz tudo, inclusive cadastros, papéis e usuários.',
    )
    acesso_vistoria = models.BooleanField('vistoria de veículos', default=False)
    acesso_checklists = models.BooleanField('checklist de equipamentos', default=False)
    acesso_termos = models.BooleanField('termos de entrada e saída de material', default=False)
    acesso_certificados = models.BooleanField('certificados (cadastro de alunos)', default=False)
    ve_todo_historico = models.BooleanField(
        'vê o histórico de todos', default=False, help_text='Desmarcado: a pessoa vê só os próprios registros.',
    )
    is_active = models.BooleanField('ativo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    ACESSOS = [
        ('administrador', 'Administrador'), ('acesso_vistoria', 'Vistoria de veículos'),
        ('acesso_checklists', 'Checklist de equipamentos'), ('acesso_termos', 'Termos'),
        ('acesso_certificados', 'Certificados'), ('ve_todo_historico', 'Histórico de todos'),
    ]

    class Meta:
        verbose_name = 'papel'
        verbose_name_plural = 'papéis'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    @property
    def acessos_texto(self):
        if self.administrador:
            return ['Acesso total']
        return [rotulo for campo, rotulo in self.ACESSOS if campo != 'administrador' and getattr(self, campo)]


# Papel padrão de quem ainda não tem um (contas antigas): o mesmo de antes, pelo campo "role".
_ACESSOS_POR_ROLE = {
    'admin': {'administrador': True},
    'tecnico': {'acesso_vistoria': True, 'acesso_checklists': True},
    'vistoriador': {'acesso_vistoria': True, 'acesso_checklists': True},
    'logistica': {'acesso_vistoria': True, 'acesso_checklists': True, 'acesso_termos': True, 've_todo_historico': True},
    'professor': {'acesso_certificados': True},
}


class User(AbstractUser):
    ROLE_ADMIN = 'admin'
    ROLE_PROFESSOR = 'professor'
    ROLE_TECNICO = 'tecnico'
    ROLE_LOGISTICA = 'logistica'
    ROLE_VISTORIADOR = 'vistoriador'  # legado: migrado para Técnico (accounts 0004)
    ROLE_PENDENTE = 'pendente'  # conta nova: sem acesso até o administrador escolher o papel
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Administrador'),
        (ROLE_TECNICO, 'Técnico (executor de checklists)'),
        (ROLE_LOGISTICA, 'Logística'),
        (ROLE_PROFESSOR, 'Professor'),
        (ROLE_PENDENTE, 'Sem papel'),
    ]

    username = None
    email = models.EmailField('e-mail', unique=True)
    full_name = models.CharField('nome completo', max_length=150)
    cpf = models.CharField('CPF', max_length=14, blank=True)
    phone = models.CharField('telefone', max_length=15, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_PENDENTE)
    is_approved = models.BooleanField('acesso aprovado', default=False)
    papel = models.ForeignKey(Papel, verbose_name='papel', on_delete=models.SET_NULL, null=True, blank=True, related_name='usuarios')
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

    # ---- Acessos: vêm do papel (Configurações → Pessoas → Papéis e acessos) ----
    def _acesso(self, campo):
        if self.is_superuser:
            return True
        if self.papel_id:
            p = self.papel
            return p.is_active and (p.administrador or getattr(p, campo))
        acessos = _ACESSOS_POR_ROLE.get(self.role, {})
        return acessos.get('administrador', False) or acessos.get(campo, False)

    @property
    def is_admin_geral(self):
        return self._acesso('administrador')

    @property
    def pode_veiculos(self):
        """Vistoria de veículos."""
        return self._acesso('acesso_vistoria')

    @property
    def pode_checklists(self):
        """Checklist de equipamentos (pré-uso, inspeção, manutenção)."""
        return self._acesso('acesso_checklists')

    @property
    def pode_termos(self):
        """Termos de entrada e saída de material."""
        return self._acesso('acesso_termos')

    @property
    def pode_certificados(self):
        """Certificados: cadastro dos alunos dos cursos (área do professor)."""
        return self._acesso('acesso_certificados')

    @property
    def ve_todo_historico(self):
        """Vê os registros de todos; sem isso, só os próprios."""
        return self._acesso('ve_todo_historico')

    @property
    def fonte_css(self):
        return FONTES.get(self.fonte, FONTES['manrope'])[1]

    @property
    def fonte_google(self):
        return FONTES.get(self.fonte, FONTES['manrope'])[2]

    @property
    def role_label(self):
        if self.papel_id:
            return self.papel.nome
        return dict(self.ROLE_CHOICES).get(self.role, self.role)
