from datetime import date, timedelta

from django.conf import settings
from django.db import models

# Itens verificados em toda inspeção, agrupados por seção (ordem de exibição).
CHECKLIST_ITEMS = [
    ('Pneus e rodas', [
        ('pneus', 'Pneus (calibragem e desgaste)'),
        ('estepe', 'Estepe'),
        ('rodas', 'Rodas e parafusos'),
    ]),
    ('Motor e fluidos', [
        ('oleo', 'Nível do óleo do motor'),
        ('agua', 'Água do radiador'),
        ('freio_fluido', 'Fluido de freio'),
        ('vazamentos', 'Sem vazamentos'),
    ]),
    ('Iluminação e sinalização', [
        ('farois', 'Faróis (baixo e alto)'),
        ('lanternas', 'Lanternas e setas'),
        ('luz_freio', 'Luz de freio e ré'),
        ('buzina', 'Buzina'),
    ]),
    ('Segurança', [
        ('freios', 'Freios e freio de mão'),
        ('cintos', 'Cintos de segurança'),
        ('extintor', 'Extintor (validade)'),
        ('triangulo', 'Triângulo, macaco e chave de roda'),
        ('painel', 'Painel sem luzes de alerta'),
    ]),
    ('Carroceria e interior', [
        ('lataria', 'Lataria sem avarias novas'),
        ('vidros', 'Vidros e retrovisores'),
        ('limpador', 'Limpador de para-brisa'),
        ('limpeza', 'Limpeza interna'),
        ('documentos', 'Documentos do veículo'),
    ]),
]
CHECKLIST_LABELS = {key: label for _, items in CHECKLIST_ITEMS for key, label in items}

# Fotos guiadas pedidas em toda inspeção: (chave, rótulo, obrigatória).
FOTO_POSICOES = [
    ('cnh', 'CNH do motorista', True),
    ('documento', 'Documento do veículo (CRLV)', True),
    ('painel', 'Painel (quadro de instrumentos)', True),
    ('frente', 'Frente', True),
    ('traseira', 'Traseira', True),
    ('lateral_esq', 'Lateral esquerda', True),
    ('lateral_dir', 'Lateral direita', True),
    ('pneu_de', 'Pneu dianteiro esquerdo', True),
    ('pneu_dd', 'Pneu dianteiro direito', True),
    ('pneu_te', 'Pneu traseiro esquerdo', True),
    ('pneu_td', 'Pneu traseiro direito', True),
]
FOTO_LABELS = {k: l for k, l, _ in FOTO_POSICOES}
# Agrupamento na tela; os pneus pedem também o estado de 0 a 100%.
FOTO_GRUPOS = [
    ('Documentos', ['cnh', 'documento']),
    ('Veículo', ['painel', 'frente', 'traseira', 'lateral_esq', 'lateral_dir']),
    ('Pneus', ['pneu_de', 'pneu_dd', 'pneu_te', 'pneu_td']),
]
PNEU_KEYS = ['pneu_de', 'pneu_dd', 'pneu_te', 'pneu_td']
PNEU_SIGLAS = {'pneu_de': 'DE', 'pneu_dd': 'DD', 'pneu_te': 'TE', 'pneu_td': 'TD'}
FOTO_ORDEM = {k: n for n, (k, _, _) in enumerate(FOTO_POSICOES)}

ITEM_OK = 'ok'
ITEM_NOK = 'nok'
ITEM_NA = 'na'
ITEM_STATUS_CHOICES = [
    (ITEM_OK, 'OK'),
    (ITEM_NOK, 'Não OK'),
    (ITEM_NA, 'N/A'),
]

TIPO_SAIDA = 'saida'
TIPO_CHEGADA = 'chegada'
TIPO_ROTINA = 'rotina'
TIPO_CHOICES = [
    (TIPO_SAIDA, 'Saída'),
    (TIPO_CHEGADA, 'Chegada'),
    (TIPO_ROTINA, 'Rotina'),
]

COMBUSTIVEL_CHOICES = [
    ('reserva', 'Reserva'),
    ('1/4', '1/4'),
    ('1/2', '1/2'),
    ('3/4', '3/4'),
    ('cheio', 'Cheio'),
]


MODULO_VEICULOS, MODULO_CHECKLISTS, MODULO_TERMOS = 'veiculos', 'checklists', 'termos'


class Supervisor(models.Model):
    """Destinatário dos e-mails do Polaris. Escolhe de quais módulos (e, nos checklists, de quais tipos) recebe."""
    name = models.CharField('nome', max_length=150)
    email = models.EmailField('e-mail', unique=True)
    recebe_veiculos = models.BooleanField('vistorias de veículos e avisos da frota', default=True)
    recebe_checklists = models.BooleanField('checklists de equipamentos', default=True)
    tipos_ativo = models.ManyToManyField(
        'checklists.TipoAtivo', verbose_name='só destes tipos de equipamento', blank=True, related_name='destinatarios',
        help_text='Deixe tudo desmarcado para receber de todos os tipos.',
    )
    recebe_termos = models.BooleanField('termos de entrada e saída', default=True)
    is_active = models.BooleanField('ativo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'destinatário'
        verbose_name_plural = 'destinatários'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} <{self.email}>'

    @classmethod
    def emails(cls, modulo=None, tipo_ativo=None):
        """E-mails de quem recebe o módulo; nos checklists, filtra pelo tipo de equipamento."""
        qs = cls.objects.filter(is_active=True)
        if modulo:
            qs = qs.filter(**{f'recebe_{modulo}': True})
        if tipo_ativo is not None:
            qs = qs.filter(models.Q(tipos_ativo=None) | models.Q(tipos_ativo=tipo_ativo))
        return list(qs.values_list('email', flat=True).distinct())


class Motorista(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name='login do técnico', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='motorista',
        help_text='Quando essa pessoa faz a vistoria, ela mesma é o motorista.',
    )
    name = models.CharField('nome', max_length=150)
    email = models.EmailField('e-mail', blank=True)
    phone = models.CharField('telefone', max_length=20, blank=True)
    cnh_numero = models.CharField('nº da CNH', max_length=20, blank=True)
    cnh_validade = models.DateField('validade da CNH', null=True, blank=True)
    is_active = models.BooleanField('ativo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'motorista'
        verbose_name_plural = 'motoristas'
        ordering = ['name']

    def __str__(self):
        return self.name


def motorista_do_usuario(user):
    """O cadastro de motorista do usuário logado (criado na primeira vistoria dele)."""
    m = Motorista.objects.filter(usuario=user).first()
    if m is None:
        m = Motorista.objects.create(usuario=user, name=user.full_name or user.email, email=user.email)
    return m


def vehicle_photo_path(instance, filename):
    return f'veiculos/fotos/{instance.placa}_{filename}'


CATEGORIA_CAMINHONETE = 'caminhonete'
CATEGORIA_CARRO = 'carro'
CATEGORIA_CHOICES = [
    (CATEGORIA_CAMINHONETE, 'Caminhonete'),
    (CATEGORIA_CARRO, 'Carro de passeio'),
]


class Veiculo(models.Model):
    placa = models.CharField('placa', max_length=8, unique=True)
    categoria = models.CharField('tipo de veículo', max_length=12, choices=CATEGORIA_CHOICES, default=CATEGORIA_CARRO)
    marca = models.CharField('marca', max_length=60)
    modelo = models.CharField('modelo', max_length=80)
    ano = models.PositiveIntegerField('ano', null=True, blank=True)
    cor = models.CharField('cor', max_length=30, blank=True)
    km_atual = models.PositiveIntegerField('km atual', default=0)
    foto = models.ImageField('foto', upload_to=vehicle_photo_path, blank=True, null=True)
    motorista_responsavel = models.ForeignKey(
        Motorista, verbose_name='motorista responsável', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='veiculos',
    )
    licenciamento_validade = models.DateField('vencimento do licenciamento', null=True, blank=True)
    seguro_validade = models.DateField('vencimento do seguro', null=True, blank=True)
    revisao_data = models.DateField('próxima revisão (data)', null=True, blank=True)
    revisao_km = models.PositiveIntegerField('próxima revisão (km)', null=True, blank=True)
    checklist_frequencia_dias = models.PositiveIntegerField(
        'checklist a cada (dias)', default=7,
        help_text='Se o veículo ficar mais que isso sem inspeção, o motorista e os supervisores recebem um lembrete.',
    )
    is_active = models.BooleanField('ativo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'veículo'
        verbose_name_plural = 'veículos'
        ordering = ['placa']

    def __str__(self):
        return f'{self.placa} · {self.marca} {self.modelo}'

    def save(self, *args, **kwargs):
        self.placa = self.placa.upper().replace(' ', '').strip()
        super().save(*args, **kwargs)

    @property
    def uso_aberto(self):
        return self.usos.filter(chegada_em__isnull=True).select_related('motorista').first()

    @property
    def ultima_inspecao(self):
        return self.inspecoes.order_by('-created_at').first()

    def vencimentos(self, dias=30):
        """Lista de (descrição, data, dias_restantes) vencidos ou vencendo em até `dias` dias.
        Itens controlados por km aparecem com data e dias = None e o km restante na descrição."""
        hoje = date.today()
        limite = hoje + timedelta(days=dias)
        itens = [
            ('Licenciamento', self.licenciamento_validade),
            ('Seguro', self.seguro_validade),
            ('Revisão', self.revisao_data),
        ]
        if self.motorista_responsavel and self.motorista_responsavel.cnh_validade:
            itens.append((f'CNH de {self.motorista_responsavel.name}', self.motorista_responsavel.cnh_validade))
        result = [(nome, d, (d - hoje).days) for nome, d in itens if d and d <= limite]
        if self.revisao_km and self.km_atual >= self.revisao_km - 500:
            result.append((f'Revisão por km ({_km(self.revisao_km)})', None, None))
        for m in self.manutencoes.filter(is_active=True):
            result += m.alertas(self.km_atual)
        return result


def _km(n):
    return f'{n:,} km'.replace(',', '.')


class Manutencao(models.Model):
    """Parâmetro de manutenção do veículo (ex.: troca de óleo a cada 10.000 km)."""
    veiculo = models.ForeignKey(Veiculo, on_delete=models.CASCADE, related_name='manutencoes')
    nome = models.CharField('nome', max_length=80, help_text='Ex.: Troca de óleo, Pneus, Correia dentada, Filtro de ar.')
    proximo_km = models.PositiveIntegerField('próxima no km', null=True, blank=True)
    proxima_data = models.DateField('próxima na data', null=True, blank=True)
    intervalo_km = models.PositiveIntegerField('repetir a cada (km)', null=True, blank=True)
    intervalo_meses = models.PositiveIntegerField('repetir a cada (meses)', null=True, blank=True)
    aviso_km = models.PositiveIntegerField('avisar quando faltarem (km)', default=1000)
    aviso_dias = models.PositiveIntegerField('avisar quando faltarem (dias)', default=15)
    is_active = models.BooleanField('ativo', default=True)

    class Meta:
        verbose_name = 'manutenção'
        verbose_name_plural = 'manutenções'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} · {self.veiculo.placa}'

    def km_restante(self, km_atual):
        return None if self.proximo_km is None else self.proximo_km - km_atual

    def alertas(self, km_atual):
        """Mesmo formato de Veiculo.vencimentos()."""
        result = []
        faltam = self.km_restante(km_atual)
        if faltam is not None and faltam <= self.aviso_km:
            texto = f'vencida há {_km(-faltam)}' if faltam < 0 else ('vence agora' if faltam == 0 else f'faltam {_km(faltam)}')
            result.append((f'{self.nome}: {texto} (no km {_km(self.proximo_km).replace(" km", "")})', None, None))
        if self.proxima_data:
            dias = (self.proxima_data - date.today()).days
            if dias <= self.aviso_dias:
                result.append((self.nome, self.proxima_data, dias))
        return result

    def registrar_feita(self, km_atual):
        """Avança para a próxima ocorrência usando os intervalos configurados."""
        if self.intervalo_km:
            self.proximo_km = km_atual + self.intervalo_km
        if self.intervalo_meses:
            hoje = date.today()
            mes = hoje.month - 1 + self.intervalo_meses
            ano, mes = hoje.year + mes // 12, mes % 12 + 1
            dia = min(hoje.day, 28)
            self.proxima_data = date(ano, mes, dia)
        self.save()


class Inspecao(models.Model):
    veiculo = models.ForeignKey(Veiculo, on_delete=models.PROTECT, related_name='inspecoes')
    motorista = models.ForeignKey(Motorista, on_delete=models.SET_NULL, null=True, blank=True, related_name='inspecoes')
    tipo = models.CharField('tipo', max_length=10, choices=TIPO_CHOICES, default=TIPO_ROTINA)
    km = models.PositiveIntegerField('km no painel')
    combustivel = models.CharField('combustível (antigo)', max_length=10, choices=COMBUSTIVEL_CHOICES, blank=True)
    combustivel_pct = models.PositiveSmallIntegerField('combustível (%)', null=True, blank=True)
    destino = models.CharField('destino / motivo', max_length=200, blank=True)
    com_carga = models.BooleanField('leva carga', null=True, blank=True, help_text='Só para caminhonetes; vazio em carro de passeio.')
    observacoes = models.TextField('observações gerais', blank=True)
    tem_problema = models.BooleanField('tem problema', default=False)
    assinatura = models.ImageField('assinatura do motorista', upload_to='veiculos/assinaturas/%Y/%m', null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField('data', auto_now_add=True)
    email_enviado = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'inspeção'
        verbose_name_plural = 'inspeções'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.veiculo.placa} · {self.get_tipo_display()} · {self.created_at:%d/%m/%Y %H:%M}'

    @property
    def carga_label(self):
        return {True: 'Sim', False: 'Não'}.get(self.com_carga, '')

    @property
    def combustivel_label(self):
        if self.combustivel_pct is not None:
            return f'{self.combustivel_pct}%'
        return self.get_combustivel_display() or '—'

    @property
    def pneus(self):
        """[(sigla, rótulo, percentual)] dos pneus fotografados, na ordem DE, DD, TE, TD."""
        por_pos = {f.posicao: f for f in self.fotos.all() if f.posicao in PNEU_KEYS}
        return [(PNEU_SIGLAS[k], FOTO_LABELS[k], por_pos[k].percentual) for k in PNEU_KEYS if k in por_pos]

    @property
    def itens_problema(self):
        return [i for i in self.itens.all() if i.status == ITEM_NOK]


class InspecaoItem(models.Model):
    inspecao = models.ForeignKey(Inspecao, on_delete=models.CASCADE, related_name='itens')
    item = models.CharField(max_length=30)
    status = models.CharField(max_length=3, choices=ITEM_STATUS_CHOICES, default=ITEM_OK)
    observacao = models.CharField('observação', max_length=255, blank=True)

    class Meta:
        unique_together = [('inspecao', 'item')]

    @property
    def label(self):
        return CHECKLIST_LABELS.get(self.item, self.item)


def inspection_photo_path(instance, filename):
    return f'veiculos/inspecoes/{instance.inspecao.created_at:%Y/%m}/{instance.inspecao_id}_{filename}'


class InspecaoFoto(models.Model):
    inspecao = models.ForeignKey(Inspecao, on_delete=models.CASCADE, related_name='fotos')
    imagem = models.ImageField(upload_to=inspection_photo_path)
    posicao = models.CharField(max_length=20, blank=True, help_text='Chave de FOTO_POSICOES; vazio para fotos extras.')
    percentual = models.PositiveSmallIntegerField('estado (%)', null=True, blank=True, help_text='Usado nos pneus: 0 a 100%.')
    legenda = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ['id']

    @property
    def titulo(self):
        base = self.legenda or FOTO_LABELS.get(self.posicao, 'Foto adicional')
        return f'{base} · {self.percentual}%' if self.percentual is not None else base


class Uso(models.Model):
    """Uma saída do veículo: aberta na inspeção de saída, fechada na de chegada."""
    veiculo = models.ForeignKey(Veiculo, on_delete=models.PROTECT, related_name='usos')
    motorista = models.ForeignKey(Motorista, on_delete=models.SET_NULL, null=True, blank=True, related_name='usos')
    destino = models.CharField('destino / motivo', max_length=200, blank=True)
    saida_em = models.DateTimeField('saída')
    km_saida = models.PositiveIntegerField('km de saída')
    chegada_em = models.DateTimeField('chegada', null=True, blank=True)
    km_chegada = models.PositiveIntegerField('km de chegada', null=True, blank=True)
    inspecao_saida = models.OneToOneField(Inspecao, on_delete=models.SET_NULL, null=True, related_name='uso_saida')
    inspecao_chegada = models.OneToOneField(Inspecao, on_delete=models.SET_NULL, null=True, blank=True, related_name='uso_chegada')

    class Meta:
        verbose_name = 'uso'
        verbose_name_plural = 'usos da frota'
        ordering = ['-saida_em']

    @property
    def km_rodados(self):
        if self.km_chegada is None:
            return None
        return self.km_chegada - self.km_saida


class AlertaEnviado(models.Model):
    """Evita mandar o mesmo alerta de vencimento/lembrete mais de uma vez."""
    chave = models.CharField(max_length=200, unique=True)
    enviado_em = models.DateTimeField(auto_now_add=True)
