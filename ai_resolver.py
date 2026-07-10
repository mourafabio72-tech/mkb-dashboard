"""
MKB AI Resolver
Versão 1.0

Este módulo será responsável por integrar o Dashboard MKB com a OpenAI
para normalização inteligente de fornecedores e clientes.

Nesta primeira versão apenas verifica se a IA está habilitada.
"""

import os


def ai_enabled():
    """
    Retorna True quando a IA estiver habilitada.
    """
    return os.getenv("AI_RESOLVER_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
        "sim",
        "on",
    )


def openai_key():
    """
    Obtém a chave da OpenAI das variáveis de ambiente.
    """
    return os.getenv("OPENAI_API_KEY", "")
