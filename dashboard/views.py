from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from accounts.models import User

_WEEKDAYS = [
    'segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira',
    'sexta-feira', 'sábado', 'domingo',
]
_MONTHS = [
    'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
]


def _resumo(user):
    """Só o que pede ação na tela inicial: veículos em uso, avisos (admin) e os últimos registros."""
    from veiculos.emails import alertas_texto
    from veiculos.models import Uso, Veiculo

    from .registros import buscar

    em_uso, n_avisos = [], 0
    if user.pode_veiculos:
        em_uso = Uso.objects.filter(chegada_em__isnull=True).select_related('veiculo', 'motorista').order_by('saida_em')
        if not user.ve_todo_historico:
            em_uso = em_uso.filter(Q(motorista__usuario=user) | Q(inspecao_saida__created_by=user))
        if user.is_admin_geral:
            n_avisos = sum(len(alertas_texto(v)) for v in Veiculo.objects.filter(is_active=True))
    return {'em_uso': list(em_uso), 'ultimos': buscar(user, limite=5), 'n_avisos': n_avisos}


def certificado_view(request):
    """Página pública com o certificado da rede local para instalar no celular (tira o aviso de site inseguro)."""
    from django.conf import settings
    from django.http import Http404, HttpResponse

    ca = settings.BASE_DIR / 'ssl_local' / 'polaris-ca.crt'
    if request.GET.get('baixar'):
        if not ca.exists():
            raise Http404
        resp = HttpResponse(ca.read_bytes(), content_type='application/x-x509-ca-cert')
        resp['Content-Disposition'] = 'attachment; filename="polaris-ca.crt"'
        return resp
    return render(request, 'dashboard/certificado.html', {'tem_certificado': ca.exists()})


@login_required
def home(request):
    from .registros import tipos_permitidos

    today = date.today()
    today_label = f'{_WEEKDAYS[today.weekday()]}, {today.day} de {_MONTHS[today.month - 1]} de {today.year}'

    context = {
        'is_admin': request.user.is_admin_geral,
        'today_label': today_label,
        'active_nav': 'inicio',
        'resumo': _resumo(request.user) if tipos_permitidos(request.user) else None,
    }
    if request.user.is_admin_geral:
        from .pendencias import listar
        context['pendencias'] = listar(request.user)
    return render(request, 'dashboard/dashboard.html', context)


# ------------------------------------------------------------ Registros (vistoria, checklist e termo juntos)

def _registros_required(view):
    from functools import wraps

    from django.core.exceptions import PermissionDenied

    from .registros import tipos_permitidos

    @wraps(view)
    @login_required
    def inner(request, *args, **kwargs):
        if not tipos_permitidos(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return inner


@_registros_required
def novo_view(request):
    """Endereço antigo do "Novo registro": a escolha agora fica na tela inicial."""
    from django.shortcuts import redirect
    from django.urls import reverse

    from .registros import TIPO_ALUNO, TIPO_CHECKLIST, TIPO_TERMO, TIPO_VISTORIA, tipos_permitidos

    opcoes_por_tipo = {
        TIPO_VISTORIA: {'titulo': 'Veículo', 'detalhe': 'Vistoria de saída, chegada ou rotina',
                        'url': reverse('veiculos:inspecao_nova')},
        TIPO_CHECKLIST: {'titulo': 'Equipamento', 'detalhe': 'Checklist de pré-uso, inspeção ou manutenção',
                         'url': reverse('checklists:executar')},
        TIPO_TERMO: {'titulo': 'Termo de material', 'detalhe': 'Entrada ou saída de material de cliente, com assinaturas',
                     'url': reverse('termos:novo')},
        TIPO_ALUNO: {'titulo': 'Certificados', 'detalhe': 'Cadastro dos alunos dos cursos', 'url': reverse('cert_prof:folders')},
    }
    opcoes = [opcoes_por_tipo[t] for t in tipos_permitidos(request.user)]
    # A escolha fica na tela inicial; com uma opção só, vai direto para ela.
    return redirect(opcoes[0]['url'] if len(opcoes) == 1 else 'dashboard:home')


@_registros_required
def historico_view(request):
    """Histórico único: tudo o que a pessoa pode ver, com filtros por tipo, texto, pessoa e período."""
    from datetime import date as _date

    from .registros import TIPOS, buscar, tipos_permitidos

    def data(nome):
        try:
            return _date.fromisoformat(request.GET.get(nome, ''))
        except ValueError:
            return None

    user = request.user
    tipo = request.GET.get('tipo', '')
    q = request.GET.get('q', '').strip()
    pessoa = None
    pessoas = []
    if user.ve_todo_historico:
        pessoas = User.objects.filter(is_active=True, is_approved=True).order_by('full_name')
        pid = request.GET.get('pessoa', '')
        pessoa = pessoas.filter(pk=pid).first() if pid.isdigit() else None
    de, ate = data('de'), data('ate')
    so_problema = request.GET.get('problema') == '1'
    registros = buscar(user, tipo, q, pessoa, de, ate)
    if so_problema:
        registros = [r for r in registros if r.problema]
    permitidos = tipos_permitidos(user)
    return render(request, 'dashboard/historico.html', {
        'active_nav': 'historico', 'registros': registros, 'tipos': [t for t in TIPOS if t[0] in permitidos],
        'f': {'tipo': tipo, 'q': q, 'pessoa': pessoa.pk if pessoa else '', 'de': de, 'ate': ate, 'problema': so_problema},
        'pessoas': pessoas, 'filtrado': bool(tipo or q or pessoa or de or ate or so_problema),
    })


@_registros_required
def concluido_view(request, tipo, pk):
    """Depois de enviar: confirmação clara e os próximos passos."""
    from django.urls import reverse

    from .registros import TIPO_CHECKLIST, TIPO_VISTORIA, como_registro, pegar

    obj = pegar(request.user, tipo, pk)
    reg = como_registro(tipo, obj)
    if tipo == TIPO_VISTORIA:
        titulo = 'Vistoria registrada'
        outro = ('Nova vistoria deste veículo', reverse('veiculos:inspecao_nova') + f'?veiculo={obj.veiculo_id}')
    elif tipo == TIPO_CHECKLIST:
        titulo = 'Checklist registrado'
        outro = ('Outro checklist neste equipamento', reverse('checklists:escolher_modelo', args=[obj.ativo_id]))
    else:
        titulo = 'Termo finalizado'
        outro = ('Novo termo', reverse('termos:novo'))
    return render(request, 'dashboard/concluido.html', {
        'active_nav': 'inicio', 'titulo': titulo, 'reg': reg, 'outro': outro,
    })


@login_required
def conferir_view(request, tipo, pk):
    """Administrador marca um equipamento novo ou um registro com problema como conferido."""
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied
    from django.shortcuts import redirect
    from django.utils.http import url_has_allowed_host_and_scheme

    from .pendencias import conferir

    if not request.user.is_admin_geral or request.method != 'POST' or tipo not in ('equipamento', 'vistoria', 'checklist'):
        raise PermissionDenied
    messages.success(request, conferir(request.user, tipo, pk))
    volta = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(volta, allowed_hosts={request.get_host()}):
        volta = '/'
    return redirect(volta)


# ------------------------------------------------------------ QR code nos equipamentos e veículos

@login_required
def qr_equipamento_view(request, pk):
    from django.shortcuts import redirect
    return redirect('checklists:escolher_modelo', ativo_pk=pk)


@login_required
def qr_veiculo_view(request, pk):
    from django.shortcuts import redirect
    from django.urls import reverse
    return redirect(reverse('veiculos:inspecao_nova') + f'?veiculo={pk}')


def _qr_svg(texto):
    import qrcode
    import qrcode.image.svg
    from django.utils.safestring import mark_safe
    img = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    svg = img.to_string(encoding='unicode')
    return mark_safe(svg[svg.index('<svg'):])


@login_required
def etiquetas_view(request):
    """Etiquetas para imprimir e colar: cada QR abre uma tela do Polaris, um equipamento ou um veículo."""
    from django.core.exceptions import PermissionDenied

    from . import qrcodes

    if not request.user.is_admin_geral:
        raise PermissionDenied
    chaves = request.GET.getlist('d')
    for nome, prefixo in [('equip', 'eq'), ('veic', 'veic')]:
        valor = request.GET.get(nome, '')
        if valor == 'todos':
            chaves += [c for g, itens in qrcodes.grupos() for c, *_ in itens if c.startswith(prefixo + ':')]
        else:
            chaves += [f'{prefixo}:{x.strip()}' for x in valor.split(',') if x.strip().isdigit()]
    etiquetas = qrcodes.etiquetas(request, chaves)
    for e in etiquetas:
        e['qr'] = _qr_svg(e['url'])
    return render(request, 'dashboard/etiquetas.html', {'etiquetas': etiquetas, 'host': qrcodes.endereco_base()})


@login_required
def qrcodes_view(request):
    """Configurações → Sistema → QR codes: escolha para onde cada QR leva e imprima as etiquetas."""
    from django.core.exceptions import PermissionDenied

    from veiculos.views import _ctx

    from . import qrcodes

    if not request.user.is_admin_geral:
        raise PermissionDenied
    return render(request, 'dashboard/qrcodes.html', _ctx(request, 'qrcodes', grupos=qrcodes.grupos(), host=qrcodes.endereco_base()))
