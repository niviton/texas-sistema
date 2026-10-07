"""
Termos de entrada e saída de material de cliente (formulários TCB-LO-01 e TCB-LO-02).

O termo registra o material que o cliente deixa na Texas (entrada) ou que a Texas entrega
ao cliente (saída), com fotos e as assinaturas do responsável Texas e do cliente.
"""
from django.conf import settings
from django.db import models

ENTRADA = 'entrada'
SAIDA = 'saida'
TIPO_CHOICES = [(ENTRADA, 'Entrada'), (SAIDA, 'Saída')]

RASCUNHO = 'rascunho'
FINALIZADO = 'finalizado'
STATUS_CHOICES = [(RASCUNHO, 'Rascunho'), (FINALIZADO, 'Finalizado')]

# Texto fixo dos formulários TCB-LO, impresso ao final de todo termo.
DECLARACAO = ('“FAÇA-SE SABER A PESSOA/EMPRESA QUE PORTA OU RECEBE ESTE MATERIAL QUE TEM A OBRIGAÇÃO DE '
              'MANTER EM BOM ESTADO E CUIDADO, JÁ QUE O SEU EXTRAVIO, QUEBRA E/OU USO INADEQUADO IMPLICA O '
              'CUSTO DE MATERIAL”')

# Rótulos que mudam conforme o tipo, como nos dois formulários.
ROTULOS = {
    ENTRADA: {'motivo': 'Motivo da entrada', 'data': 'Data da entrada'},
    SAIDA: {'motivo': 'Motivo da entrega', 'data': 'Data da saída'},
}
PADRAO_DOCUMENTO = {
    ENTRADA: ('TCB-LO-01', 'Termo de entrada - material cliente'),
    SAIDA: ('TCB-LO-02', 'Termo de saída - material cliente'),
}


class ModeloTermo(models.Model):
    """Controle do documento (cabeçalho do PDF) de cada tipo de termo."""
    tipo = models.CharField('tipo', max_length=10, choices=TIPO_CHOICES, unique=True)
    codigo = models.CharField('código do documento', max_length=40)
    titulo = models.CharField('título', max_length=200)
    revisao = models.CharField('revisão', max_length=5, default='00')
    preparado_por = models.CharField('preparado por', max_length=120, blank=True)
    revisado_por = models.CharField('revisado por', max_length=120, blank=True)
    data = models.DateField('data', null=True, blank=True)

    class Meta:
        verbose_name = 'documento de termo'
        verbose_name_plural = 'documentos de termo'
        ordering = ['tipo']

    def __str__(self):
        return f'{self.codigo} rev. {self.revisao}'

    @classmethod
    def do_tipo(cls, tipo):
        codigo, titulo = PADRAO_DOCUMENTO[tipo]
        return cls.objects.get_or_create(tipo=tipo, defaults={'codigo': codigo, 'titulo': titulo})[0]


class Termo(models.Model):
    tipo = models.CharField('tipo', max_length=10, choices=TIPO_CHOICES, default=ENTRADA)
    status = models.CharField('status', max_length=12, choices=STATUS_CHOICES, default=RASCUNHO)
    numero_assunto = models.CharField('nº do assunto', max_length=60, blank=True)
    motivo = models.CharField('motivo', max_length=200, blank=True)
    data = models.DateField('data')
    cliente_contato = models.CharField('cliente e pessoa de contato', max_length=200)
    origem = models.CharField('origem (projeto / parque específico)', max_length=200, blank=True)
    transporte = models.CharField('transporte', max_length=120, blank=True)
    observacoes = models.TextField('observações', blank=True)
    assinatura_texas = models.ImageField('assinatura do responsável Texas', upload_to='termos/assinaturas/%Y/%m', null=True, blank=True)
    responsavel_texas = models.CharField('responsável Texas', max_length=150, blank=True)
    assinatura_cliente = models.ImageField('assinatura do cliente', upload_to='termos/assinaturas/%Y/%m', null=True, blank=True)
    nome_cliente = models.CharField('nome legível do cliente', max_length=150, blank=True)
    telefone_cliente = models.CharField('telefone do cliente', max_length=30, blank=True)
    documento = models.ForeignKey(ModeloTermo, on_delete=models.PROTECT, null=True, related_name='termos',
                                  help_text='Revisão do documento usada ao finalizar (cabeçalho do PDF).')
    documento_revisao = models.CharField(max_length=5, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    email_enviado = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'termo'
        verbose_name_plural = 'termos'
        ordering = ['-data', '-created_at']

    def __str__(self):
        return f'Termo de {self.get_tipo_display().lower()} nº {self.numero}'

    @property
    def numero(self):
        return f'{self.pk:05d}' if self.pk else '—'

    @property
    def rotulos(self):
        return ROTULOS[self.tipo]

    @property
    def finalizado(self):
        return self.status == FINALIZADO

    def pendencias_para_finalizar(self):
        faltas = []
        if not self.itens.exists():
            faltas.append('inclua pelo menos um equipamento')
        if not self.assinatura_texas:
            faltas.append('falta a assinatura do responsável Texas')
        if not self.assinatura_cliente:
            faltas.append('falta a assinatura do cliente')
        if not self.nome_cliente.strip():
            faltas.append('informe o nome legível do cliente')
        return faltas


class TermoItem(models.Model):
    termo = models.ForeignKey(Termo, on_delete=models.CASCADE, related_name='itens')
    descricao = models.CharField('equipamento', max_length=200)
    referencia = models.CharField('referência', max_length=120, blank=True)
    quantidade = models.PositiveIntegerField('quantidade', default=1)
    informacao = models.CharField('informação', max_length=200, blank=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordem', 'id']


def foto_termo_path(instance, filename):
    return f'termos/fotos/{instance.termo.created_at:%Y/%m}/{instance.termo_id}_{filename}'


class TermoFoto(models.Model):
    termo = models.ForeignKey(Termo, on_delete=models.CASCADE, related_name='fotos')
    imagem = models.ImageField(upload_to=foto_termo_path)

    class Meta:
        ordering = ['id']
