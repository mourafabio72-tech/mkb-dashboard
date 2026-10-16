FROM python:3.12-slim

# Usuario sem privilegio. O processo do app roda como ele, nunca como root.
RUN groupadd -g 1000 app && useradd -u 1000 -g 1000 -M -d /app -s /usr/sbin/nologin app

WORKDIR /app
# O WORKDIR nasce de root. Sem DB_PATH o banco cai em /app, e o app precisa
# conseguir criar arquivo ali.
RUN chown app:app /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --chown preserva o mtime, entao o carimbo de versao (versao.py) continua igual.
COPY --chown=app:app . .

# Entrada fora do /app e de dono root: o usuario app nao consegue reescrever
# o script que roda como root no proximo start.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

# Banco SQLite fica em /data (volume persistente configurado no Easypanel,
# sobrevive a rebuilds/redeploys do container)
ENV DB_PATH=/data/mkb_dre.db
ENV PORT=8000
EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "wsgi.py"]
