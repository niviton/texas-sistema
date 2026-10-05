from django.core.management.base import BaseCommand, CommandError

from checklists.importador import FormularioInvalido, importar
from checklists.models import TipoAtivo


class Command(BaseCommand):
    help = 'Importa formulários TCB-OTB (.docx) como modelos de checklist. Ex.: python manage.py importar_tcb tcbs/*.docx'

    def add_arguments(self, parser):
        parser.add_argument('arquivos', nargs='+')
        parser.add_argument('--tipo', help='Nome do tipo de ativo (criado se não existir). Padrão: deduzido do título.')

    def handle(self, *args, **opts):
        tipo = TipoAtivo.objects.get_or_create(nome=opts['tipo'])[0] if opts.get('tipo') else None
        for caminho in opts['arquivos']:
            try:
                modelo, revisao, criado = importar(caminho, tipo)
            except FormularioInvalido as exc:
                raise CommandError(f'{caminho}: {exc}')
            n = revisao.itens().count()
            acao = 'criado' if criado else 'atualizado'
            self.stdout.write(self.style.SUCCESS(
                f'{modelo.codigo} rev. {revisao.rotulo} {acao}: "{modelo.titulo}", {revisao.secoes.count()} seções, {n} itens, '
                f'aplica-se a: {", ".join(t.nome for t in modelo.tipos_ativo.all())}'
            ))
