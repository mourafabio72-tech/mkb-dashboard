"""
wsgi.py — MKB-Dashboard
Entry point para produção (waitress).
Usado pelo Render: start command = "python wsgi.py"

Em desenvolvimento use: python app.py
"""

import os
from waitress import serve
from app import app
from ingestion import get_conn, criar_schema, seed_empresas
from config import PORT

if __name__ == "__main__":
    # Inicializa banco e tabelas antes de subir o servidor
    conn = get_conn()
    criar_schema(conn)
    seed_empresas(conn)
    conn.close()

    host = "0.0.0.0"
    port = int(os.environ.get("PORT", PORT))

    print(f"\n  MKB-Dashboard (produção) rodando em http://{host}:{port}")
    print(f"  Waitress — servidor de produção WSGI\n")

    serve(app, host=host, port=port, threads=4)
