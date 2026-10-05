---
tipo: notas_lidas
projeto: FinHub (_deploy_mkb)
gerado_em: 2026-10-05 20:10
metodo: leitura direta pelo principal + 5 batedores sonnet em paralelo (fichas) + 1 batedor do código
---

# Notas lidas na descoberta do "Pergunte à IA"

Caminhos relativos a `/Users/fabiomoura/ObsidianJovi/`. "Principal" = lida integral pelo agente
principal. "Batedor" = lida integral pelo batedor, que devolveu ficha; reler integral antes de
escrever o arquivo que ela rege (Leitura_e_Retencao, regra 8).

| # | Nota | Linhas | Quem leu | Trecho-chave | Fase |
|---|---|---|---|---|---|
| 1 | `00B_DOUTRINAS/Anti_Puxa_Saco.md` | 189 | principal | "Fale a verdade util, nao a verdade agradavel." | todas |
| 2 | `00B_DOUTRINAS/Leitura_e_Retencao_de_Notas.md` | 236 | principal | "Nota da vault se le INTEIRA." | todas |
| 3 | `01_SISTEMAS/08_Processo_Dev/Brainstorming_Socratico_por_Tarefa.md` | 97 | principal | 2 a 4 perguntas, opções objetivas, padrão declarado | abertura |
| 4 | `01_SISTEMAS/07_Regras_de_Ouro/Escada_Preguica_de_Codigo.md` | 241 | principal | "A escada decide o COMO, nunca o SE." | plano, 2-5 |
| 5 | `01_SISTEMAS/01_Padroes_Gerais/Padrao_CLAUDE_MD_Projeto.md` | 182 | principal | bloco da vault no topo, convenções do projeto depois | 1 |
| 6 | `01_SISTEMAS/01_Padroes_Gerais/Padrao_Graphify_Projeto_Novo.md` | 68 | principal | `--code-only`; `claude install` apensa ao CLAUDE.md | 1, 6 |
| 7 | `00A_MAPAS/_TEMPLATE_GENESIS/*` | 326 | principal | molde dos 6 arquivos | abertura |
| 8 | `01_SISTEMAS/02_Seguranca/Vazamento_de_Chaves.md` | 84 | principal (conferência) + batedor | "NUNCA no código-fonte, NUNCA no template, NUNCA no JS do front-end." | 2 |
| 9 | `01_SISTEMAS/02_Seguranca/Mapa_de_Conceitos_de_Seguranca.md` | 509 | batedor; principal conferiu linhas 474-499 por triagem | "nunca `\| safe` em output de LLM, nunca concatenar output de LLM em SQL, sempre system prompt separado do user input, rate limit em endpoint de IA" | 3, 4 |
| 10 | `02_Seguranca/Revisao_Vulnerabilidades.md` | 36 | batedor | "Nenhuma chave de API pode chegar ao navegador." | 2-4 |
| 11 | `02_Seguranca/Padrao_Validacao_de_Input.md` | 197 | batedor | "Toda string crua passa por validação tipada antes de tocar regra de negócio." | 3 |
| 12 | `02_Seguranca/Padrao_Mass_Assignment.md` | 210 | batedor | whitelist; o resto é ignorado | 3, 4 |
| 13 | `02_Seguranca/Padrao_IDOR.md` | 199 | batedor | validar direito ao recurso antes de devolver | 3, 4 |
| 14 | `02_Seguranca/Padrao_Logging_Estruturado.md` | 210 | batedor | "Senha, token e PII NUNCA entram em log." | 2-4 |
| 15 | `02_Seguranca/CSRF_Cookies_Headers.md` | 117 | batedor | token em todo POST | 2-4 |
| 16 | `02_Seguranca/Controle_de_IP.md` | 68 | batedor | rate limit em POST (o FinHub usa o ÚLTIMO XFF, ver B03 da vault do Fábio) | 3 |
| 17 | `02_Seguranca/Padrao_Dependencias_Lockfile.md` | 219 | batedor | versão pinada | 2 |
| 18 | `02_Seguranca/Padrao_Container_Seguro.md` | 268 | batedor | segredo nunca em ENV/ARG do Dockerfile | 2 |
| 19 | `02_Seguranca/Principios.md` | 48 | batedor | rota com dado privado exige login | 2-4 |
| 20 | `03_Auth_Perfis_Permissoes/Painel_Desenvolvedor.md` | 164 | batedor | chaves de API no grupo Desenvolvedor (conflito decidido: admin) | 2 |
| 21 | `03_Auth_Perfis_Permissoes/Matriz_VER_EDITAR.md` | 132 | batedor | só VER e EDITAR, sem ação nova | 2, 3 |
| 22 | `03_Auth_Perfis_Permissoes/Perfis_e_Modulos.md` | 85 | batedor | rota protegida aponta para chave de módulo (o FinHub usa role) | 2, 3 |
| 23 | `03_Auth_Perfis_Permissoes/Admin_Inicial_Padrao.md` | 214 | batedor | "Nunca republicar credencial em nota, README ou CLAUDE.md." | 1, 2 |
| 24 | `01_Padroes_Gerais/Padrao_Marca_IA.md` | 306 | batedor | `ph-sparkle`, família `#7C3AED`, `.bloco-ia`, `.btn-ia`, `.tag-ia` | 5 |
| 25 | `07_Regras_de_Ouro/Sempre_Marcar_IA.md` | 96 | batedor (2x) | "IA é sempre roxa"; exceção da tela técnica | 5 |
| 26 | `01_Padroes_Gerais/Sistema_de_Estilos.md` | 215 | batedor | sem CSS inline, hex só em tokens | 5 |
| 27 | `01_Padroes_Gerais/Icones_Phosphor.md` | 174 | batedor | sem emoji; tamanho via CSS | 5 |
| 28 | `01_Padroes_Gerais/Padrao_Toggle_Tipos.md` | 167 | batedor | 3 tipos, perguntar; escolhido tipo 2 | 5 |
| 29 | `01_Padroes_Gerais/Padrao_Formulario.md` | 188 | batedor | controles 40px, label 13px 600 | 5 |
| 30 | `01_Padroes_Gerais/Acao_Primaria_a_Direita.md` | 162 | batedor | âncora no CSS do container | 5 |
| 31 | `01_Padroes_Gerais/Padrao_Box_Card.md` | 225 | batedor | flex column, token, hover sem background | 5 |
| 32 | `01_Padroes_Gerais/Padrao_Loading_Estado.md` | 341 | batedor | gerúndio específico, finally | 5 |
| 33 | `07_Regras_de_Ouro/Sempre_Mostrar_Loading.md` | 94 | batedor | proibido "Carregando...", "Aguarde..." | 5 |
| 34 | `01_Padroes_Gerais/Padrao_Tabela.md` | 609 | batedor | regra 1: mais de 10 linhas ganha menu | 3, 5 |
| 35 | `01_Padroes_Gerais/Padrao_Cabecalho_da_Tabela.md` | 210 | batedor | título dentro do card, contagem no cabeçalho | 5 |
| 36 | `01_Padroes_Gerais/Padrao_Estado_Vazio.md` | 219 | batedor | `.vz`, "Nenhum Resultado" | 5 |
| 37 | `01_Padroes_Gerais/Padrao_KPI_Dashboard.md` | 247 | batedor | KPI só em dashboard | 5 |
| 38 | `07_Regras_de_Ouro/Listagens_sem_KPI.md` | 74 | batedor | nada de KPI em listagem | 5 |
| 39 | `01_Padroes_Gerais/Componente_SelectBusca.md` | 84 | batedor | nunca `<select>` | 5 |
| 40 | `07_Regras_de_Ouro/Sem_Select_Nativo.md` | 66 | batedor | "Sem exceção." | 5 |
| 41 | `01_Padroes_Gerais/Padrao_Modal.md` | 406 | batedor | estrutura do modal | 5 (se houver modal) |
| 42 | `01_Padroes_Gerais/Padrao_Modal_Nao_Fecha_Sozinho.md` | 213 | batedor | só X e Cancelar fecham | 5 (se houver modal) |
| 43 | `01_Padroes_Gerais/Padrao_Acao_Primaria_na_Topbar.md` | 120 | batedor | "+ Novo" na topbar (não há neste trabalho) | 5 |
| 44 | `07_Regras_de_Ouro/Revisao_Professor_Pasquale.md` | 152 | batedor | acentuação, UTF-8, zero travessão | 5 |
| 45 | `07_Regras_de_Ouro/Portugues_BR_Acentuacao.md` | 165 | batedor | identificador sem acento, texto com acento | 5 |
| 46 | `07_Regras_de_Ouro/Sem_Travessao.md` | 43 | batedor | nunca `—` | todas |
| 47 | `Padrao_Texto_e_Linguagem.md` (pacote do plugin, `base_conhecimento/01_SISTEMAS/01_Padroes_Gerais/`) | 256 | batedor | verbo + objeto; erro diz o que fazer | 5 |

## Notas consideradas e descartadas

- `Padrao_Menu_Sidebar` (580), `Padrao_Sidebar_Rodape` (286): o FinHub não tem menu lateral.
- `Padrao_Modal_Popup_Centrado` (172): sem SelectBusca em modal.
- `Padrao_Upload_Arquivo` (345): sem arquivo.
- `Padrao_Toggle_OnOff` (234): nenhuma escolha é liga/desliga.
- `Padrao_Tabs` (185): Perguntar/Analisar muda o que a operação faz, então é toggle, não aba.
- `Padrao_Barra_de_Filtros` (418), `Padrao_Paginacao_Servidor` (154), `Padrao_Filtro_por_Coluna` (183): sem barra de filtro e resultado limitado a 10 linhas.
- `Padrao_Convite_de_Acesso` (293), `Auto_Liberacao_por_Grupo` (83), `Instrucao_Replicar_Sistema_Perfis` (548): o FinHub usa roles.
- `Padrao_Impersonacao_Segura`, `Timeout_de_Sessao`, `Forca_Bruta_Login`, `Padrao_CI_CD_Seguro`: fora do escopo.
- `70_ESTILO/Padroes_Linguagem/Vocabulario_Proibido.md` (211, pacote do plugin): redundante com `Padrao_Texto_e_Linguagem`.

## Não encontradas

- `Padrao_AI_Security`: não existe na vault (o Mapa_de_Conceitos diz que será criada).
- `Padrao_Texto_e_Linguagem` e a pasta `70_ESTILO/` não existem em `/Users/fabiomoura/ObsidianJovi`; só no pacote do plugin.
- `scripts/pasquale.py` não existe na vault: vale o fallback por `grep` + leitura.
- Nota de campo de chave/segredo com botão Testar: não encontrada; vale `Padrao_Formulario` + `Padrao_Loading_Estado`.
