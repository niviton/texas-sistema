"""Fila de conferência do administrador: equipamentos cadastrados na hora e registros com problema."""
from django.utils import timezone

from .registros import TIPO_CHECKLIST, TIPO_VISTORIA, como_registro


def _consultas():
    from checklists.models import Ativo, Execucao
    from veiculos.models import Inspecao
    equipamentos = Ativo.objects.filter(conferido=False, is_active=True).select_related('tipo', 'cadastrado_por')
    vistorias = Inspecao.objects.filter(tem_problema=True, conferido_em__isnull=True).select_related('veiculo', 'motorista')
    execucoes = Execucao.objects.filter(tem_problema=True, conferido_em__isnull=True).select_related('ativo__tipo', 'revisao__modelo')
    return equipamentos, vistorias, execucoes


def contar(user):
    if not getattr(user, 'is_admin_geral', False):
        return 0
    return sum(q.count() for q in _consultas())


def listar(user, limite=12):
    if not user.is_admin_geral:
        return {'equipamentos': [], 'registros': [], 'total': 0}
    equipamentos, vistorias, execucoes = _consultas()
    registros = [como_registro(TIPO_VISTORIA, v) for v in vistorias.order_by('-created_at')[:limite]]
    registros += [como_registro(TIPO_CHECKLIST, e) for e in execucoes.order_by('-created_at')[:limite]]
    registros.sort(key=lambda r: r.quando, reverse=True)
    return {'equipamentos': list(equipamentos[:limite]), 'registros': registros[:limite],
            'total': equipamentos.count() + vistorias.count() + execucoes.count()}


def conferir(user, tipo, pk):
    from django.shortcuts import get_object_or_404

    from checklists.models import Ativo, Execucao
    from veiculos.models import Inspecao
    if tipo == 'equipamento':
        obj = get_object_or_404(Ativo, pk=pk)
        obj.conferido = True
        obj.save(update_fields=['conferido'])
        return f'{obj.nome} conferido.'
    modelo = {TIPO_VISTORIA: Inspecao, TIPO_CHECKLIST: Execucao}[tipo]
    obj = get_object_or_404(modelo, pk=pk)
    obj.conferido_em, obj.conferido_por = timezone.now(), user
    obj.save(update_fields=['conferido_em', 'conferido_por'])
    return 'Registro marcado como conferido.'
