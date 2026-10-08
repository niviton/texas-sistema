"""
Motor genérico de checklists do Polaris.

Um checklist da empresa é sempre: um *modelo* (formulário controlado TCB-OTB, com revisão)
aplicado a um *ativo* (equipamento real) por um técnico, gerando uma *execução*.
Novos checklists entram cadastrando modelos, sem programação. Veja docs/modulos/checklists.md.
"""
from django.conf import settings
from django.db import models

MEDIDOR_NENHUM = 'nenhum'
MEDIDOR_HORIMETRO = 'horimetro'
MEDIDOR_KM = 'km'
MEDIDOR_CHOICES = [
    (MEDIDOR_NENHUM, 'Sem medidor'),
    (MEDIDOR_HORIMETRO, 'Horímetro (horas)'),
    (MEDIDOR_KM, 'Quilometragem (km)'),
]
MEDIDOR_UNIDADE = {MEDIDOR_HORIMETRO: 'h', MEDIDOR_KM: 'km'}

STATUS_DISPONIVEL = 'disponivel'
STATUS_EM_USO = 'em_uso'
STATUS_MANUTENCAO = 'manutencao'
STATUS_INATIVO = 'inativo'
STATUS_ATIVO_CHOICES = [
    (STATUS_DISPONIVEL, 'Disponível'),
    (STATUS_EM_USO, 'Em uso'),
    (STATUS_MANUTENCAO, 'Em manutenção'),
    (STATUS_INATIVO, 'Inativo'),
]

# Tipos de resposta de um item. Cada um define as opções e quais contam como problema.
RESP_OK_NOK = 'ok_nok'
RESP_CONFORMIDADE = 'conformidade'
RESP_SIM_NAO = 'sim_nao'
RESP_PORCENTAGEM = 'porcentagem'
RESP_NUMERO = 'numero'
RESP_TEXTO = 'texto'
TIPO_RESPOSTA_CHOICES = [
    (RESP_OK_NOK, 'OK / NOK / N/A'),
    (RESP_CONFORMIDADE, 'Conforme / Não conforme / Parcialmente / N/A'),
    (RESP_SIM_NAO, 'Sim / Não'),
    (RESP_PORCENTAGEM, 'Porcentagem (0 a 100%)'),
    (RESP_NUMERO, 'Número'),
    (RESP_TEXTO, 'Texto livre'),
]
OPCOES_RESPOSTA = {
    RESP_OK_NOK: [('ok', 'OK'), ('nok', 'NOK'), ('na', 'N/A')],
    RESP_CONFORMIDADE: [('conforme', 'Conforme'), ('nao_conforme', 'Não conforme'), ('parcial', 'Parcialmente'), ('na', 'N/A')],
    RESP_SIM_NAO: [('sim', 'Sim'), ('nao', 'Não')],
}
VALORES_NEGATIVOS = {'nok', 'nao_conforme', 'parcial'}
ROTULO_VALOR = {v: rotulo for opcoes in OPCOES_RESPOSTA.values() for v, rotulo in opcoes}

OBS_NUNCA = 'nunca'
OBS_SE_NEGATIVO = 'se_negativo'
OBS_SEMPRE = 'sempre'
OBS_CHOICES = [
    (OBS_SE_NEGATIVO, 'Só quando a resposta for negativa'),
    (OBS_SEMPRE, 'Sempre'),
    (OBS_NUNCA, 'Nunca'),
]


class TipoAtivo(models.Model):
    nome = models.CharField('nome', max_length=120, unique=True,
                            help_text='Família de equipamentos, ex.: Gerador, Chave elétrica de torque, Transpaleteira.')
    medidor = models.CharField('medidor', max_length=12, choices=MEDIDOR_CHOICES, default=MEDIDOR_NENHUM,
                               help_text='Leitura pedida em toda execução (ex.: horímetro do gerador).')
    descricao = models.CharField('descrição', max_length=255, blank=True)
    is_active = models.BooleanField('ativo', default=True)

    class Meta:
        verbose_name = 'tipo de ativo'
        verbose_name_plural = 'tipos de ativo'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Ativo(models.Model):
    tipo = models.ForeignKey(TipoAtivo, verbose_name='tipo', on_delete=models.PROTECT, related_name='ativos')
    nome = models.CharField('nome', max_length=150, help_text='Como o equipamento é conhecido, ex.: Bancada RAD 02.')
    identificacao = models.CharField('identificação / nº de série', max_length=80, blank=True)
    patrimonio = models.CharField('patrimônio', max_length=40, blank=True)
    marca = models.CharField('marca', max_length=80, blank=True)
    modelo = models.CharField('modelo', max_length=80, blank=True)
    status = models.CharField('status', max_length=12, choices=STATUS_ATIVO_CHOICES, default=STATUS_DISPONIVEL)
    medidor_atual = models.DecimalField('leitura atual do medidor', max_digits=10, decimal_places=1, null=True, blank=True)
    observacoes = models.TextField('observações', blank=True)
    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='cadastrado por', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', help_text='Preenchido quando o técnico cadastra o equipamento na hora do checklist.',
    )
    is_active = models.BooleanField('ativo', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ativo'
        verbose_name_plural = 'ativos'
        ordering = ['tipo__nome', 'nome']

    def __str__(self):
        return f'{self.nome} ({self.identificacao})' if self.identificacao else self.nome

    def modelos_disponiveis(self):
        return Modelo.objects.filter(is_active=True, tipos_ativo=self.tipo).order_by('codigo')


FINALIDADE_PRE_USO, FINALIDADE_INSPECAO, FINALIDADE_MANUTENCAO, FINALIDADE_GERAL = 'pre_uso', 'inspecao', 'manutencao', 'geral'
FINALIDADE_CHOICES = [
    (FINALIDADE_PRE_USO, 'Pré-uso'),
    (FINALIDADE_INSPECAO, 'Inspeção'),
    (FINALIDADE_MANUTENCAO, 'Manutenção'),
    (FINALIDADE_GERAL, 'Geral'),
]
# Texto curto mostrado no primeiro passo de "Executar".
FINALIDADE_DESCRICAO = {
    FINALIDADE_PRE_USO: 'Antes de usar o equipamento',
    FINALIDADE_INSPECAO: 'Inspeção periódica do equipamento',
    FINALIDADE_MANUTENCAO: 'Registro da manutenção preventiva',
    FINALIDADE_GERAL: 'Checklist geral do equipamento',
}


def finalidade_do_titulo(titulo):
    """'Checklist de pré-uso – Prensa' -> 'pre_uso'. Usado na importação dos TCB."""
    t = (titulo or '').lower().replace('é', 'e').replace('ç', 'c').replace('ã', 'a').replace('-', ' ')
    if 'pre uso' in t:
        return FINALIDADE_PRE_USO
    if 'inspec' in t:
        return FINALIDADE_INSPECAO
    if 'manutenc' in t:
        return FINALIDADE_MANUTENCAO
    return FINALIDADE_GERAL


class Modelo(models.Model):
    """Formulário controlado (ex.: TCB-OTB-80). O conteúdo fica nas revisões."""
    codigo = models.CharField('código do documento', max_length=40, unique=True, help_text='Ex.: TCB-OTB-80')
    titulo = models.CharField('título', max_length=200, help_text='Ex.: Checklist de pré-uso – Bancada de calibração')
    finalidade = models.CharField('finalidade', max_length=12, choices=FINALIDADE_CHOICES, default=FINALIDADE_GERAL,
                                  help_text='Primeiro passo do técnico ao executar: pré-uso, inspeção, manutenção ou geral.')
    tipos_ativo = models.ManyToManyField(TipoAtivo, verbose_name='aplica-se a', related_name='modelos', blank=True)
    is_active = models.BooleanField('disponível para execução', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'modelo de checklist'
        verbose_name_plural = 'modelos de checklist'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} · {self.titulo}'

    @property
    def revisao_vigente(self):
        return self.revisoes.filter(vigente=True).order_by('-numero').first()


class Revisao(models.Model):
    """Uma versão do formulário. Revisão já usada em execuções não é mais editada: cria-se a próxima."""
    modelo = models.ForeignKey(Modelo, on_delete=models.CASCADE, related_name='revisoes')
    numero = models.PositiveSmallIntegerField('revisão', default=0)
    preparado_por = models.CharField('preparado por', max_length=120, blank=True)
    revisado_por = models.CharField('revisado por', max_length=120, blank=True)
    data = models.DateField('data', null=True, blank=True)
    vigente = models.BooleanField('vigente', default=True)
    notas = models.CharField('o que mudou', max_length=255, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'revisão'
        verbose_name_plural = 'revisões'
        ordering = ['modelo__codigo', '-numero']
        constraints = [models.UniqueConstraint(fields=['modelo', 'numero'], name='revisao_unica_por_modelo')]

    def __str__(self):
        return f'{self.modelo.codigo} rev. {self.rotulo}'

    @property
    def rotulo(self):
        return f'{self.numero:02d}'

    @property
    def em_uso(self):
        return self.execucoes.exists()

    def itens(self):
        return Item.objects.filter(secao__revisao=self).order_by('secao__ordem', 'secao_id', 'ordem', 'id')

    def criar_proxima(self, notas=''):
        """Copia seções e itens para a revisão seguinte e a torna vigente."""
        nova = Revisao.objects.create(
            modelo=self.modelo, numero=self.numero + 1, preparado_por=self.preparado_por,
            revisado_por=self.revisado_por, data=None, vigente=True, notas=notas,
        )
        for secao in self.secoes.all():
            itens = list(secao.itens.all())
            secao.pk = None
            secao.revisao = nova
            secao.save()
            for item in itens:
                item.pk = None
                item.secao = secao
                item.save()
        Revisao.objects.filter(modelo=self.modelo).exclude(pk=nova.pk).update(vigente=False)
        return nova


class Secao(models.Model):
    revisao = models.ForeignKey(Revisao, on_delete=models.CASCADE, related_name='secoes')
    titulo = models.CharField('título', max_length=150)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordem', 'id']

    def __str__(self):
        return self.titulo


class Item(models.Model):
    secao = models.ForeignKey(Secao, on_delete=models.CASCADE, related_name='itens')
    texto = models.CharField('item', max_length=255)
    tipo_resposta = models.CharField('tipo de resposta', max_length=16, choices=TIPO_RESPOSTA_CHOICES, default=RESP_OK_NOK)
    exige_foto = models.BooleanField('exige foto', default=False)
    observacao = models.CharField('pede observação', max_length=12, choices=OBS_CHOICES, default=OBS_SE_NEGATIVO)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordem', 'id']

    def __str__(self):
        return self.texto

    @property
    def opcoes(self):
        return OPCOES_RESPOSTA.get(self.tipo_resposta, [])


class Execucao(models.Model):
    revisao = models.ForeignKey(Revisao, on_delete=models.PROTECT, related_name='execucoes')
    ativo = models.ForeignKey(Ativo, on_delete=models.PROTECT, related_name='execucoes')
    executor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='execucoes_checklist')
    executor_nome = models.CharField('técnico', max_length=150)
    medidor_valor = models.DecimalField('leitura do medidor', max_digits=10, decimal_places=1, null=True, blank=True)
    observacoes = models.TextField('observações', blank=True)
    assinatura = models.ImageField('assinatura do técnico', upload_to='checklists/assinaturas/%Y/%m', null=True, blank=True)
    tem_problema = models.BooleanField(default=False)
    email_enviado = models.BooleanField(default=False)
    created_at = models.DateTimeField('data', auto_now_add=True)

    class Meta:
        verbose_name = 'execução de checklist'
        verbose_name_plural = 'execuções de checklist'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.revisao.modelo.codigo} · {self.ativo} · {self.created_at:%d/%m/%Y}'

    @property
    def modelo(self):
        return self.revisao.modelo

    @property
    def problemas(self):
        return [r for r in self.respostas.all() if r.negativa]

    @property
    def medidor_label(self):
        if self.medidor_valor is None:
            return ''
        valor = f'{self.medidor_valor:,.1f}'.replace(',', 'X').replace('.', ',').replace('X', '.').removesuffix(',0')
        return f'{valor} {MEDIDOR_UNIDADE.get(self.ativo.tipo.medidor, "")}'.strip()


class Resposta(models.Model):
    execucao = models.ForeignKey(Execucao, on_delete=models.CASCADE, related_name='respostas')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='respostas')
    valor = models.CharField(max_length=255, blank=True)
    observacao = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['item__secao__ordem', 'item__secao_id', 'item__ordem', 'item_id']

    @property
    def negativa(self):
        return self.valor in VALORES_NEGATIVOS

    @property
    def rotulo(self):
        if self.item.tipo_resposta == RESP_PORCENTAGEM and self.valor != '':
            return f'{self.valor}%'
        return ROTULO_VALOR.get(self.valor, self.valor) or '—'


def foto_execucao_path(instance, filename):
    return f'checklists/fotos/{instance.execucao.created_at:%Y/%m}/{instance.execucao_id}_{filename}'


class FotoExecucao(models.Model):
    execucao = models.ForeignKey(Execucao, on_delete=models.CASCADE, related_name='fotos')
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    imagem = models.ImageField(upload_to=foto_execucao_path)
    legenda = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['id']

    @property
    def titulo(self):
        return self.legenda or (self.item.texto if self.item else 'Foto do equipamento')
