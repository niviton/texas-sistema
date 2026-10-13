"""
Registros do Polaris vistos como uma coisa só: vistoria de veículo, checklist de equipamento e termo.
Usado pelo "Novo registro", pelo histórico único e pela tela de "concluído".
"""
from dataclasses import dataclass
from datetime import datetime, time

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

TIPO_VISTORIA, TIPO_CHECKLIST, TIPO_TERMO = 'vistoria', 'checklist', 'termo'
TIPOS = [(TIPO_VISTORIA, 'Vistoria de veículo'), (TIPO_CHECKLIST, 'Checklist de equipamento'), (TIPO_TERMO, 'Termo de material')]


@dataclass
class Registro:
    tipo: str
    pk: int
    quando: datetime
    titulo: str
    detalhe: str
    pessoa: str
    problema: bool
    url: str
    pdf_url: str
    rascunho: bool = False

    @property
    def tipo_label(self):
        return dict(TIPOS)[self.tipo]


def tipos_permitidos(user):
    tipos = []
    if user.pode_veiculos:
        tipos.append(TIPO_VISTORIA)
    if user.pode_checklists:
        tipos.append(TIPO_CHECKLIST)
    if user.pode_termos:
        tipos.append(TIPO_TERMO)
    return tipos


# ------------------------------------------------------------ consultas visíveis para cada pessoa

def _vistorias(user):
    from veiculos.models import Inspecao
    qs = Inspecao.objects.select_related('veiculo', 'motorista', 'created_by')
    if not user.ve_todo_historico:
        qs = qs.filter(Q(created_by=user) | Q(motorista__usuario=user))
    return qs


def _execucoes(user):
    from checklists.models import Execucao
    qs = Execucao.objects.select_related('ativo__tipo', 'revisao__modelo', 'executor')
    if not user.ve_todo_historico:
        qs = qs.filter(executor=user)
    return qs


def _termos(user):
    from termos.models import Termo
    return Termo.objects.select_related('created_by')


def _de_vistoria(v):
    return Registro(TIPO_VISTORIA, v.pk, v.created_at, v.veiculo.placa,
                    f'Vistoria de {v.get_tipo_display().lower()} · {v.veiculo.marca} {v.veiculo.modelo}'.strip(),
                    v.motorista.name if v.motorista else '', v.tem_problema,
                    reverse('veiculos:inspecao_detalhe', args=[v.pk]), reverse('veiculos:inspecao_pdf', args=[v.pk]))


def _de_execucao(e):
    m = e.revisao.modelo
    return Registro(TIPO_CHECKLIST, e.pk, e.created_at, e.ativo.nome, f'{m.get_finalidade_display()} · {m.codigo}',
                    e.executor_nome, e.tem_problema,
                    reverse('checklists:execucao', args=[e.pk]), reverse('checklists:execucao_pdf', args=[e.pk]))


def _de_termo(t):
    return Registro(TIPO_TERMO, t.pk, t.finalizado_em or t.created_at, f'Termo nº {t.numero}',
                    f'{t.get_tipo_display()} · {t.cliente_contato}',
                    (t.created_by.full_name or t.created_by.email) if t.created_by else '', False,
                    reverse('termos:detalhe', args=[t.pk]) if t.finalizado else reverse('termos:editar', args=[t.pk]),
                    reverse('termos:pdf', args=[t.pk]), rascunho=not t.finalizado)


def buscar(user, tipo='', q='', pessoa=None, de=None, ate=None, limite=300):
    """Lista única, do mais recente para o mais antigo, com os filtros do histórico."""
    permitidos = tipos_permitidos(user)
    tipos = [tipo] if tipo in permitidos else permitidos
    inicio = timezone.make_aware(datetime.combine(de, time.min)) if de else None
    fim = timezone.make_aware(datetime.combine(ate, time.max)) if ate else None
    regs = []

    def periodo(qs, campo='created_at'):
        if inicio:
            qs = qs.filter(**{f'{campo}__gte': inicio})
        if fim:
            qs = qs.filter(**{f'{campo}__lte': fim})
        return qs

    if TIPO_VISTORIA in tipos:
        qs = periodo(_vistorias(user))
        if q:
            qs = qs.filter(Q(veiculo__placa__icontains=q) | Q(veiculo__modelo__icontains=q) | Q(veiculo__marca__icontains=q)
                           | Q(motorista__name__icontains=q) | Q(observacoes__icontains=q))
        if pessoa:
            qs = qs.filter(Q(created_by=pessoa) | Q(motorista__usuario=pessoa))
        regs += [_de_vistoria(v) for v in qs.order_by('-created_at')[:limite]]
    if TIPO_CHECKLIST in tipos:
        qs = periodo(_execucoes(user))
        if q:
            qs = qs.filter(Q(ativo__nome__icontains=q) | Q(ativo__identificacao__icontains=q) | Q(ativo__patrimonio__icontains=q)
                           | Q(ativo__tipo__nome__icontains=q) | Q(revisao__modelo__codigo__icontains=q)
                           | Q(executor_nome__icontains=q) | Q(observacoes__icontains=q))
        if pessoa:
            qs = qs.filter(executor=pessoa)
        regs += [_de_execucao(e) for e in qs.order_by('-created_at')[:limite]]
    if TIPO_TERMO in tipos:
        qs = periodo(_termos(user))
        if q:
            qs = qs.filter(Q(cliente_contato__icontains=q) | Q(numero_assunto__icontains=q) | Q(motivo__icontains=q)
                           | Q(origem__icontains=q) | Q(itens__descricao__icontains=q)).distinct()
        if pessoa:
            qs = qs.filter(created_by=pessoa)
        regs += [_de_termo(t) for t in qs.order_by('-created_at')[:limite]]
    regs.sort(key=lambda r: r.quando, reverse=True)
    return regs[:limite]


def pegar(user, tipo, pk):
    """Um registro visível para a pessoa (404 se não puder ver)."""
    if tipo not in tipos_permitidos(user):
        from django.http import Http404
        raise Http404
    if tipo == TIPO_VISTORIA:
        return get_object_or_404(_vistorias(user), pk=pk)
    if tipo == TIPO_CHECKLIST:
        return get_object_or_404(_execucoes(user), pk=pk)
    return get_object_or_404(_termos(user), pk=pk)


def como_registro(tipo, obj):
    return {TIPO_VISTORIA: _de_vistoria, TIPO_CHECKLIST: _de_execucao, TIPO_TERMO: _de_termo}[tipo](obj)
