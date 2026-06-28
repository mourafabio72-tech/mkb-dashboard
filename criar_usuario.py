"""
criar_usuario.py — MKB-Dashboard
Cria ou atualiza (reset de senha/role) um usuário direto no banco, sem
precisar da tela web /usuarios -- útil pra criar o 1º admin num servidor
novo (VPS) ou resetar uma senha esquecida.

Uso:
    python criar_usuario.py --usuario fabio --nome "Fabio Moura" --senha "SenhaForte123" --role admin
    python criar_usuario.py --usuario fabio --senha "NovaSenha456"   # reset de senha (mantém role/nome)
"""

import argparse
from werkzeug.security import generate_password_hash

from ingestion import get_conn, criar_schema


def main():
    parser = argparse.ArgumentParser(description="Cria ou atualiza um usuário do MKB-Dashboard")
    parser.add_argument("--usuario", required=True, help="Login (curto, ex.: fabio)")
    parser.add_argument("--nome", help="Nome completo (obrigatório se o usuário ainda não existir)")
    parser.add_argument("--email", default=None)
    parser.add_argument("--senha", required=True)
    parser.add_argument("--role", choices=["admin", "leitura"], default=None,
                        help="Só altera o role se informado (mantém o atual em reset de senha)")
    args = parser.parse_args()

    conn = get_conn()
    criar_schema(conn)

    existente = conn.execute("SELECT id, role FROM usuarios WHERE usuario=?", (args.usuario,)).fetchone()
    senha_hash = generate_password_hash(args.senha)

    if existente:
        role = args.role or existente["role"]
        conn.execute(
            "UPDATE usuarios SET senha_hash=?, role=?, ativo=1"
            + (", nome=?" if args.nome else "")
            + (", email=?" if args.email else "")
            + " WHERE usuario=?",
            tuple(
                [senha_hash, role]
                + ([args.nome] if args.nome else [])
                + ([args.email] if args.email else [])
                + [args.usuario]
            ),
        )
        conn.commit()
        print(f"Usuário \"{args.usuario}\" atualizado (role={role}).")
    else:
        if not args.nome:
            print("Usuário novo precisa de --nome.")
            conn.close()
            return
        conn.execute(
            "INSERT INTO usuarios (usuario, nome, email, senha_hash, role, ativo) VALUES (?,?,?,?,?,1)",
            (args.usuario, args.nome, args.email, senha_hash, args.role or "leitura"),
        )
        conn.commit()
        print(f"Usuário \"{args.usuario}\" criado (role={args.role or 'leitura'}).")

    conn.close()


if __name__ == "__main__":
    main()
