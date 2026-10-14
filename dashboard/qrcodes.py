"""
Destinos de QR code: telas do Polaris (ex.: "Pré-uso › Gerador") e equipamentos ou veículos específicos.
Usado pela tela Configurações → Sistema → QR codes e pela página de etiquetas para imprimir.
Cada destino tem uma chave curta (ex.: "pag:historico", "tipo:pre_uso:3", "eq:12").
"""
from django.urls import reverse

ACAO_PAGINA = 'Aponte a câmera para abrir'


def _paginas():
    from checklists.models import FINALIDADE_CHOICES, Modelo, TipoAtivo

    grupos = [
        ('Geral', [
            ('pag:inicio', 'Tela inicial', 'Novo registro, pendências e últimos registros', reverse('dashboard:home')),
            ('pag:historico', 'Histórico', 'Todos os registros com filtros', reverse('dashboard:historico')),
        ]),
        ('Vistoria de veículo', [
            ('pag:veiculo', 'Vistoria de veículo', 'Escolher saída, chegada ou rotina', reverse('veiculos:inspecao_nova')),
            ('pag:veiculo:saida', 'Vistoria de saída', 'Pegar um veículo', reverse('veiculos:inspecao_nova') + '?tipo=saida'),
            ('pag:veiculo:chegada', 'Vistoria de chegada', 'Devolver o veículo', reverse('veiculos:inspecao_nova') + '?tipo=chegada'),
            ('pag:veiculo:rotina', 'Vistoria de rotina', 'Vistoria periódica', reverse('veiculos:inspecao_nova') + '?tipo=rotina'),
        ]),
    ]
    checklist = [('pag:checklist', 'Checklist de equipamento', 'Escolher pré-uso, inspeção ou manutenção', reverse('checklists:executar'))]
    modelos = Modelo.objects.filter(is_active=True, revisoes__vigente=True).distinct()
    for valor, rotulo in FINALIDADE_CHOICES:
        tipos = TipoAtivo.objects.filter(is_active=True, modelos__in=modelos.filter(finalidade=valor)).distinct().order_by('nome')
        if not tipos:
            continue
        checklist.append((f'fin:{valor}', f'Checklist de {rotulo.lower()}', 'Escolher o tipo de equipamento',
                          reverse('checklists:passo_tipo', args=[valor])))
        checklist += [(f'tipo:{valor}:{t.pk}', f'{rotulo} › {t.nome}', 'Escolher qual equipamento',
                       reverse('checklists:passo_ativo', args=[valor, t.pk])) for t in tipos]
    grupos.append(('Checklist de equipamento', checklist))
    grupos.append(('Termos de material', [
        ('pag:termo', 'Novo termo', 'Entrada ou saída de material de cliente', reverse('termos:novo')),
        ('pag:termos', 'Lista de termos', 'Termos já registrados', reverse('termos:lista')),
    ]))
    grupos.append(('Certificados', [
        ('pag:certificados', 'Certificados', 'Cadastro dos alunos (professor)', reverse('cert_prof:folders')),
    ]))
    return grupos


def _equipamentos():
    from checklists.models import Ativo
    return [(f'eq:{a.pk}', a.nome, ' · '.join(x for x in [a.tipo.nome, a.identificacao, a.patrimonio] if x),
             reverse('dashboard:qr_equipamento', args=[a.pk]))
            for a in Ativo.objects.filter(is_active=True).select_related('tipo').order_by('tipo__nome', 'nome')]


def _veiculos():
    from veiculos.models import Veiculo
    return [(f'veic:{v.pk}', v.placa, f'{v.marca} {v.modelo}'.strip(), reverse('dashboard:qr_veiculo', args=[v.pk]))
            for v in Veiculo.objects.filter(is_active=True).order_by('placa')]


def grupos():
    """Para a tela de escolha: [(grupo, [(chave, titulo, detalhe, caminho)])]."""
    return _paginas() + [('Um equipamento específico', _equipamentos()), ('Um veículo específico', _veiculos())]


def endereco_base():
    """Endereço do servidor que vai no QR (SITE_URL), e não o endereço por onde a tela foi aberta:
    gerar a etiqueta pelo próprio computador (127.0.0.1) não pode produzir um QR que só funciona nele."""
    from django.conf import settings
    return settings.SITE_URL.rstrip('/')


def etiquetas(request, chaves):
    """Etiquetas das chaves escolhidas, na ordem da tela, com o endereço completo no QR."""
    escolhidas = set(chaves)
    base = endereco_base()
    saida = []
    for grupo, itens in grupos():
        for chave, titulo, detalhe, caminho in itens:
            if chave not in escolhidas:
                continue
            if chave.startswith('eq:'):
                acao = 'Aponte a câmera para fazer o checklist'
            elif chave.startswith('veic:'):
                acao = 'Aponte a câmera para fazer a vistoria'
            else:
                acao = ACAO_PAGINA
            saida.append({'titulo': titulo, 'sub': detalhe, 'acao': acao, 'url': base + caminho})
    return saida
