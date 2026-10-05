# LOG do FinHub (MKB-Dashboard)

Diario de bordo. O 00_GENESIS nasceu aqui no cerco de seguranca de 2026-08-29
(o app e anterior ao fluxo Genesis); por ora guarda o diario do cerco.

[2026-08-29] jerico rodada=1 acao=ataque_simulado resultado=2_achados obs="Cerco genesis-jerico no FinHub. App subido em 127.0.0.1:5055 (banco de teste vazio, schema criado no boot; app.py forca 0.0.0.0, subi via runner com bind 127.0.0.1 pra cumprir a regra). Atores: jerico_admin (admin, via DASHBOARD_USERS), jerico_leitura (leitura, injetado), e sessao SSO forjada restrita a MKB (cookie assinado com SECRET_KEY de teste). LIMPO: isolamento por empresa (guard _guard_empresa aborta 403 em GNILEB para cliente restrito a MKB, tanto <empresa> no path quanto ?empresa= na query, 16 rotas testadas), RBAC (admin_required em /usuarios/*, /ingest, /endividamento* de escrita: leitura levou 302->/ em tudo), IDOR usuarios (so admin gerencia, sem troca de ID por nao-admin), upload/path traversal (/ingest usa tempfile.NamedTemporaryFile(suffix=Path(filename).suffix); nome do usuario nao vira caminho; try/except evita 500/stack; sem rota de download parametrizado), SSRF (unica saida e OpenAI SDK, destino fixo), SQLi (queries com ?; bypass de login ' OR 1=1 nao autentica; payloads em competencia/empresa sem 500 nem vazamento de sqlite_version)."
[2026-08-29] jerico rodada=1 ATAQUE csrf-ausente em POST (todos) | payload=admin logado POST /usuarios/novo SEM token csrf (nome+email+senha+role=admin) | prova=usuario 'csrfpoc' role=admin criado, 302->/usuarios; form nao tem nenhum campo csrf (grep csrf no app.py=0) | severidade=MEDIA (mitigada por SameSite=Lax, que barra POST cross-site em navegador moderno) | nota=CSRF_Cookies_Headers | rotas=/login, /usuarios/novo, /usuarios/<id>/senha, /usuarios/<id>/alternar, /ingest, /endividamento* | CONSERTO=NAO na marra: portar o security.py do Hub exige tocar os 14 templates com form (adicionar {{ csrf_token }}); e mini-projeto proprio, levado ao operador
[2026-08-29] jerico rodada=1 ATAQUE rate-limit por remote_addr em /login | payload=5 logins errados esgotam o balde e o 6o login CORRETO leva "Muitas tentativas. Aguarde 299s" | prova=app.py:537 usa request.remote_addr direto, nao le X-Forwarded-For; atras do Traefik do EasyPanel remote_addr e sempre o IP do proxy, entao TODOS os clientes caem no mesmo balde: um cliente errando trava o login de todos (DoS) e o limite nao distingue clientes | severidade=BAIXA-MEDIA (robustez/disponibilidade, nao bypass) | nota=Forca_Bruta_Login | rotas=app.py:537 | CONSERTO=rodada correcao 1: ler o ULTIMO XFF com fallback remote_addr (mesmo padrao aplicado no Hub em 29/08)
[2026-08-29] jerico rodada=correcao1 CONSERTO furo=rate-limit-remote_addr | mudanca=app.py: nova funcao _ip_cliente() que le o ULTIMO X-Forwarded-For (fallback remote_addr); o /login passou a chavear o rate_limit_login por ela em vez de request.remote_addr | prova=cliente A (XFF ...,1.1.1.1) errando 5x foi bloqueado (200 "Aguarde 282s"); cliente B (XFF ...,2.2.2.2) logou normal (302) no mesmo instante = baldes separados por cliente, nao mais balde unico do proxy | nota=Forca_Bruta_Login (mesmo padrao do Hub em 29/08)
[2026-08-29] jerico rodada=2 acao=ataque_verificacao resultado=rate-limit_fechado obs="Rate-limit reatacado e confirmado por cliente. CSRF ausente PERMANECE por decisao: fechar exige portar o guard do Hub e tocar os 14 templates com form; nao se faz na marra dentro do cerco. Levado ao operador. Isolamento/RBAC/upload/SSRF/SQLi seguem limpos."

[2026-09-17 18:21] jerico cerco=FinHub(_deploy_mkb) | estatica + ataque dinamico local (127.0.0.1, sqlite descartavel, py3.12)
  ESTATICA: SQL com placeholder ? nos valores; f-string so no NOME da tabela (_tabela_lancamentos, valor do
    codigo, nao do request) -> sem SQLi. /usuarios/* com @login_required+@admin_required. Cookie HttpOnly+SameSite=Lax
    (Secure so no dominio zoaria/prod). after_request so poe Cache-Control.
  ATAQUE rodada=1:
    - AUTH: /, /dre/<comp>, /api/lancamentos-razao, /usuarios, /balanco sem sessao -> 302 login. LIMPO.
    - PRIVILEGIO: usuario role 'leitura' -> GET /usuarios, POST /usuarios/novo, POST /usuarios/1/senha
      todos 302 pro index (admin_required), hacker NAO criado. LIMPO.
    - SQLi: aspas em /dre e /api/lancamentos-razao -> sem 500/erro SQL. LIMPO (parametrizado).
    ACHADOS CONFIRMADOS:
    - [MEDIO] CSRF AUSENTE: POST /usuarios/novo autenticado SEM token -> 302 e usuario criado no banco.
      Nenhum token/validacao CSRF no app (so o comentario do /health cita). Atenuado por SameSite=Lax
      (bloqueia cookie em POST cross-site em navegador moderno), mas e controle de servidor ausente.
      Conserto: token por sessao + secrets.compare_digest em POST/PUT/PATCH/DELETE, igual security.py do CRM.
    - [BAIXO-MEDIO] HEADERS DE SEGURANCA AUSENTES: sem X-Frame-Options (clickjacking do dashboard DRE),
      sem X-Content-Type-Options, sem CSP, sem HSTS, sem Referrer-Policy. Conserto: after_request com os 6
      headers, igual ao _seguranca_after do CRM.
  RESULTADO: 2 achados (1 medio CSRF, 1 baixo-medio headers). Auth, privilegio e SQLi limpos. Nao consertado
    nesta sessao: decisao do dono (app de producao); conserto proposto acima.

[2026-09-18 14:15] jerico conserto=FinHub headers | achado [BAIXO-MEDIO] fechado: novo after_request _headers_seguranca
  poe X-Frame-Options SAMEORIGIN, X-Content-Type-Options nosniff, Referrer-Policy, HSTS e Permissions-Policy
  (setdefault, nao sobrescreve). CSP DEIXADA DE FORA de proposito: dashboard usa <script> inline
  ({{ grafico_serie|safe }}), CSP script-src 'self' quebraria os graficos; CSP exige nonce, tarefa a parte.
  Provado no local: os 5 headers saem em /login e /; GET / (dashboard) -> 200 (nao quebrou). CSRF [MEDIO]
  segue em aberto por decisao do dono. Nao commitado nem publicado: fica pro fluxo de deploy do Fabio.

[JERICO 2026-09-18 18:35] conserto=FinHub CSRF | achado [MEDIO] fechado. Token por sessao (get_csrf_token), before_request
  _csrf_protect valida X-CSRF-Token OU campo csrf_token com secrets.compare_digest em POST/PUT/PATCH/DELETE;
  isento login/logout/health/static. Front (base.html): meta csrf-token + patch no fetch (header) + listener
  de submit que injeta campo oculto em todo form POST (cobre os ~15 forms sem editar cada um). Provado local:
  POST /usuarios/novo sem token -> 400; com token -> 302 e cria; login isento -> 302; GET livre. Nao commitado.
