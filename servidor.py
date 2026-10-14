"""
Liga o Polaris como servidor da oficina, em modo produção.

    python servidor.py        (ou pythonw servidor.py, sem janela: é assim que o Windows inicia sozinho)

O log fica em logs/servidor.log. Se o servidor cair, ele é reiniciado depois de alguns segundos.
"""
import os
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(BASE)
sys.path.insert(0, str(BASE))
os.environ['DJANGO_DEBUG'] = 'False'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

(BASE / 'logs').mkdir(exist_ok=True)
log = open(BASE / 'logs' / 'servidor.log', 'a', encoding='utf-8', buffering=1)
if sys.stdout is None or not sys.stdout.isatty():  # pythonw (sem janela): tudo vai para o log
    sys.stdout = sys.stderr = log


def porta_ocupada(porta):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', porta)) == 0


if porta_ocupada(8443):
    print(f'{datetime.now():%d/%m/%Y %H:%M} Porta 8443 já em uso: o Polaris já está rodando.', file=log)
    sys.exit(0)

from django.core.management import execute_from_command_line  # noqa: E402

while True:
    print(f'{datetime.now():%d/%m/%Y %H:%M:%S} Iniciando o Polaris...', flush=True)
    try:
        execute_from_command_line(['manage.py', 'servidor'])
        break  # parada normal (Ctrl+C)
    except KeyboardInterrupt:
        break
    except SystemExit as exc:
        if exc.code in (0, None):
            break
        print(f'{datetime.now():%d/%m/%Y %H:%M:%S} O servidor parou (código {exc.code}). Reiniciando em 10 s.', flush=True)
    except Exception as exc:  # noqa: BLE001 - qualquer falha: registra e tenta de novo
        print(f'{datetime.now():%d/%m/%Y %H:%M:%S} Erro: {exc!r}. Reiniciando em 10 s.', flush=True)
    time.sleep(10)
