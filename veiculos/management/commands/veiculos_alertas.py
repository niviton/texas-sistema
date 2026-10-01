from django.core.management.base import BaseCommand

from veiculos.emails import enviar_alertas


class Command(BaseCommand):
    help = (
        'Envia aos supervisores os alertas de vencimento (licenciamento, seguro, revisão, CNH) '
        'e os lembretes de checklist atrasado. Agende para rodar uma vez por dia.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dias', type=int, default=30, help='Antecedência dos alertas de vencimento (padrão: 30).')

    def handle(self, *args, **opts):
        venc, lemb = enviar_alertas(opts['dias'])
        self.stdout.write(self.style.SUCCESS(f'{venc} vencimento(s) e {lemb} lembrete(s) enviados.'))
