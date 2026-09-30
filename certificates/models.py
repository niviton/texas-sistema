from django.conf import settings
from django.db import models

CERT_TYPE_INTERNO = 'interno'
CERT_TYPE_EXTERNO = 'externo'
CERT_TYPE_CHOICES = [
    (CERT_TYPE_INTERNO, 'Interno'),
    (CERT_TYPE_EXTERNO, 'Externo'),
]

STATUS_PENDING = 'pendente'
STATUS_APPROVED = 'aprovado'
STATUS_REJECTED = 'rejeitado'
STATUS_CHOICES = [
    (STATUS_PENDING, 'Pendente'),
    (STATUS_APPROVED, 'Aprovado'),
    (STATUS_REJECTED, 'Rejeitado'),
]


def signature_upload_path(instance, filename):
    return f'signatures/{instance.sigla or "professor"}_{filename}'


class Professor(models.Model):
    full_name = models.CharField('nome completo', max_length=150)
    sigla = models.CharField('sigla', max_length=4, unique=True)
    signature = models.ImageField('assinatura', upload_to=signature_upload_path, blank=True, null=True)
    is_active = models.BooleanField(
        'ativo', default=True,
        help_text='Professores arquivados não aparecem para seleção em novos certificados, mas o histórico é mantido.',
    )
    is_chief = models.BooleanField('é instrutor chefe', default=False)
    chief_cert_type = models.CharField(
        'tipo de certificado (instrutor chefe)', max_length=10, choices=CERT_TYPE_CHOICES, blank=True,
    )
    signature_offset_x_pt = models.IntegerField(
        'deslocamento horizontal da assinatura (pt)', default=0,
        help_text='Positivo move para a direita, negativo para a esquerda.',
    )
    signature_offset_y_pt = models.IntegerField(
        'deslocamento vertical da assinatura (pt)', default=0,
        help_text='Positivo move para baixo, negativo para cima (mais perto do nome).',
    )
    signature_light_threshold = models.PositiveIntegerField(
        'limite de branco (0-255)', default=225,
        help_text='Pixels mais claros que isso viram transparentes. Diminua se a assinatura ficar com fundo esbranquiçado; aumente se partes do traço estiverem sumindo.',
    )
    signature_dark_threshold = models.PositiveIntegerField(
        'limite de preto (0-255)', default=60,
        help_text='Pixels mais escuros que isso ficam totalmente opacos (tom mais forte). Aumente para deixar o traço mais escuro/nítido.',
    )
    signature_invert_colors = models.BooleanField(
        'assinatura com fundo escuro (inverter)', default=False,
        help_text='Ative se a assinatura enviada for traço claro sobre fundo escuro, em vez de tinta escura sobre papel claro.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'professor'
        verbose_name_plural = 'professores'
        ordering = ['full_name']
        constraints = [
            models.UniqueConstraint(
                fields=['chief_cert_type'],
                condition=models.Q(is_chief=True) & ~models.Q(chief_cert_type=''),
                name='one_chief_per_cert_type',
            ),
        ]

    def __str__(self):
        return f'{self.full_name} ({self.sigla})'

    def save(self, *args, **kwargs):
        self.sigla = self.sigla.upper().strip()
        if not self.is_chief:
            self.chief_cert_type = ''
        super().save(*args, **kwargs)

    @classmethod
    def chief_for(cls, cert_type):
        return cls.objects.filter(is_chief=True, chief_cert_type=cert_type).first()


class CourseTemplate(models.Model):
    title = models.CharField('título do curso', max_length=200)
    default_subject_number = models.CharField('número do assunto padrão', max_length=9, blank=True)
    syllabus_items = models.TextField('conteúdo programático', blank=True, help_text='Um item por linha')
    default_duration = models.CharField('duração padrão', max_length=50, blank=True)
    word_template = models.FileField('modelo em Word', upload_to='course_templates/word/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'modelo de certificado'
        verbose_name_plural = 'modelos de certificado'
        ordering = ['title']

    def __str__(self):
        return self.title

    @property
    def syllabus_list(self):
        return [line.strip() for line in self.syllabus_items.splitlines() if line.strip()]


class StudentRegistration(models.Model):
    student_name = models.CharField('nome do aluno', max_length=150)
    cpf = models.CharField('CPF', max_length=14)
    course_template = models.ForeignKey(CourseTemplate, on_delete=models.PROTECT, related_name='registrations')
    professor = models.ForeignKey(Professor, on_delete=models.PROTECT, related_name='registrations')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='cert_registrations',
    )
    subject_code = models.CharField('assunto', max_length=9)
    client_name = models.CharField(
        'cliente / local do curso', max_length=150, blank=True,
        help_text='Ex: nome da empresa ou unidade onde o curso foi dado.',
    )
    course_date = models.DateField('data do curso')
    duration = models.CharField('duração', max_length=50)
    cert_type = models.CharField(max_length=10, choices=CERT_TYPE_CHOICES, default=CERT_TYPE_INTERNO)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'cadastro de aluno'
        verbose_name_plural = 'cadastros de alunos'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.student_name} — {self.subject_code}'

    def save(self, *args, **kwargs):
        self.student_name = self.student_name.upper().strip()
        super().save(*args, **kwargs)


class Certificate(models.Model):
    code = models.CharField('código', max_length=40, unique=True)
    student_name = models.CharField('nome do aluno', max_length=150)
    cpf = models.CharField('CPF', max_length=14, blank=True)
    course_template = models.ForeignKey(
        CourseTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name='certificates',
    )
    course_title = models.CharField('curso', max_length=200)
    client_name = models.CharField(
        'cliente / local do curso', max_length=150, blank=True,
        help_text='Ex: nome da empresa ou unidade onde o curso foi dado.',
    )
    professor = models.ForeignKey(
        Professor, on_delete=models.PROTECT, null=True, blank=True, related_name='certificates',
    )
    instructor_name = models.CharField('instrutor', max_length=150, blank=True)
    subject_code = models.CharField('assunto', max_length=9, blank=True)
    cert_type = models.CharField(max_length=10, choices=CERT_TYPE_CHOICES, default=CERT_TYPE_INTERNO)
    course_date = models.DateField('data do curso')
    duration = models.CharField('duração', max_length=50)
    issue_date = models.DateField('data de emissão')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='certificates_created',
    )
    source_registration = models.OneToOneField(
        StudentRegistration, on_delete=models.SET_NULL, null=True, blank=True, related_name='certificate',
    )
    external_link = models.CharField(
        'link externo do certificado', max_length=500, blank=True,
        help_text='Se preenchido, "Ver" no Histórico abre este link (ex: SharePoint) em vez do PDF gerado pelo sistema.',
    )

    class Meta:
        verbose_name = 'certificado'
        verbose_name_plural = 'certificados'
        ordering = ['-issue_date']

    def __str__(self):
        return f'{self.code} — {self.student_name}'

    def save(self, *args, **kwargs):
        self.code = self.code.upper().strip()
        self.student_name = self.student_name.upper().strip()
        if self.professor and not self.instructor_name:
            self.instructor_name = self.professor.full_name
        super().save(*args, **kwargs)

    @staticmethod
    def build_code(subject_code, sigla):
        prefix = f'TC-FO-{subject_code}-{sigla}-'
        max_seq = 0
        for code in Certificate.objects.filter(code__startswith=prefix).values_list('code', flat=True):
            suffix = code[len(prefix):]
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))
        return f'{prefix}{max_seq + 1:02d}'


class CertificateSettings(models.Model):
    show_qr_code = models.BooleanField('mostrar QR code de verificação', default=True)
    signature_width_pt = models.PositiveIntegerField('largura padrão da assinatura (pt)', default=120)
    signature_height_pt = models.PositiveIntegerField('altura padrão da assinatura (pt)', default=50)

    class Meta:
        verbose_name = 'configurações de certificado'
        verbose_name_plural = 'configurações de certificado'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Configurações de certificado'
