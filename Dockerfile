FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Banco SQLite fica em /data (volume persistente configurado no Easypanel,
# sobrevive a rebuilds/redeploys do container)
ENV DB_PATH=/data/mkb_dre.db
ENV PORT=8000
EXPOSE 8000

CMD ["python", "wsgi.py"]
