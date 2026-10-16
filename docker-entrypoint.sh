#!/bin/sh
# Entrada do container: acerta o dono do volume e larga o root.
#
# POR QUE EXISTE: ate 2026-10 o FinHub rodava como root, e o volume /data de
# producao (mkb_dre.db e os arquivos de chave e config da IA, que moram no
# diretorio do banco) nasceu com arquivos de root. O processo agora roda como o
# usuario app (1000), que nao grava em arquivo de root. Este script roda como
# root SO o tempo de passar o dono para app, e troca de usuario antes de subir
# o Python. Mesmo padrao do Zoaria Hub (a401203).
#
# O chown so acontece quando acha arquivo de outro dono, entao do segundo start
# em diante nao custa nada. Nao apaga, nao move, nao muda permissao: muda o dono.
set -e

APP_UID=1000
APP_GID=1000

if [ "$(id -u)" = "0" ]; then
    alvo="$(dirname "${DB_PATH:-/data/mkb_dre.db}")"
    case "$alvo" in
        /|/app|/etc|/usr|/proc|/sys)
            echo "entrypoint: recusado ajustar dono de '$alvo'" >&2
            exit 1 ;;
    esac
    mkdir -p "$alvo"
    if [ -n "$(find "$alvo" \( ! -user "$APP_UID" -o ! -group "$APP_GID" \) -print -quit)" ]; then
        echo "entrypoint: passando $alvo para app ($APP_UID:$APP_GID)"
        chown -R "$APP_UID:$APP_GID" "$alvo"
    fi
    exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --init-groups "$@"
fi

exec "$@"
