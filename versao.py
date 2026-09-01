"""
Carimbo de versao e build, para saber DE FORA o que producao esta servindo.

POR QUE EXISTE: em 2026-09-01 o XmlHub revelou que o repositorio dele nao tinha
webhook no GitHub. Seis commits ficaram parados no servidor sem nenhum sinal:
site respondendo 200, historico do EasyPanel cheio de "Success", e o container
antigo servindo. Um deles ja tinha sido dado como publicado. So se descobriu
porque aquele app ganhou este carimbo horas antes.

Sem isto, a unica forma de saber qual versao esta no ar e entrar no app ou no
painel. Com isto, um curl responde:

    curl -s https://dre.zoaria.com.br/login | grep -oE "build [0-9]{8}-[0-9]{4}"

O carimbo vem do mtime deste arquivo. No container ele nasce do arquivo do
commit, entao o carimbo BATE COM A DATA DO COMMIT e identifica o ponto exato
da historia que esta servido. Nao depende de variavel de ambiente, que alguem
esqueceria de atualizar.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

_ESTE_ARQUIVO = Path(__file__).resolve()

# -03:00 fixo em vez do banco de fusos: o Brasil nao tem horario de verao desde
# 2019, e o container pode subir sem tzdata.
_FUSO_BR = timezone(timedelta(hours=-3))


def _carimbo_de_build() -> str:
    """AAAAMMDD-HHMM no relogio de Brasilia. Falha vira 'desconhecido'."""
    try:
        quando = datetime.fromtimestamp(_ESTE_ARQUIVO.stat().st_mtime, _FUSO_BR)
        return quando.strftime("%Y%m%d-%H%M")
    except OSError:
        return "desconhecido"


BUILD = _carimbo_de_build()

#: O que aparece na tela: "build 20260901-1046".
VERSAO_COMPLETA = f"build {BUILD}"