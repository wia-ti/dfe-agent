# PLAN_SPRINT7.md

> Plano de remediacao para os erros de CLI observados em 2026-08-26.
> Origem: tentativas de executar `python -m src.query --hybrid "<pergunta sobre RTC>"`
> a partir do PowerShell do usuario, apos o agente ter falhado a consulta ao RAG.
> Itens cobertos: **2 BLOQUEANTE** + **2 IMPORTANTE** + **1 PARCIAL** (5 total).
> Principio: **TDD** (teste vermelho primeiro), zero regressao nas suites existentes,
> cobertura >= 80%.
>
> NAO cobre a consulta ao RAG em si (filtros de top-k, reranker, BM25 tuning) nem
> o conteudo da base sobre RTC NF-e (NT 2025.002): para isso o usuario precisa
> primeiro conseguir rodar o CLI sem erro — premissa deste plano.

## Criterio global de conclusao

`pytest tests/ --cov=src --cov-fail-under=80` retorna exit code 0 **E** os 2 BLOQUEANTE
sao verificados manualmente pelos comandos shell documentados em "Verificacao manual dos
BLOQUEANTE" no fim deste plano **E** os 2 IMPORTANTE tem teste automatizado cobrindo o
desvio **E** o `tests/unit/query/test_main.py` existente (`_run_cli`) e substituido por
um helper compartilhado que delega ao mesmo bootstrap que o CLI real usa (sem duplicar
o workaround de `PYTHONPATH` entre conftest e os testes).

```
Fase A ──► Fase B ──► Fase C ──► Fase D ──► Fase E
sys.path     stdout      diagnose    query      finalize
bootstrap    utf-8       col. net    cleanup    docs
BLOQUEANTE   BLOQUEANTE  IMPORTANTE  IMPORTANTE PARCIAL
```

**Dependencias criticas entre fases**:

- B (encoding de stdout) depende de A (sys.path) — sem A, B nao consegue nem rodar o
  subprocess que reproduz o erro.
- D (cleanup de "(no output)") depende de B (stdout utf-8) — o sintoma de "no output"
  e' quase certamente o mesmo `UnicodeEncodeError` engolido.
- C (diagnostico de rede no coletor) e independente de A/B.
- E (docs) depende de A+B+C+D.

---

## Resumo dos erros observados

| ID | Sintoma | Comando que dispara | Causa raiz (resumo) |
|----|---------|---------------------|---------------------|
| **B7** | `ModuleNotFoundError: No module named 'hooks'` -> `RuntimeError("domain_guard indisponivel; guardrail exige-o")` | `python -m src.query --hybrid "..."` direto do PowerShell | `src/utils/http_guard.py:38` faz `from hooks.domain_guard import ...`; o pacote `hooks` vive em `.opencode/hooks/`. Testes resolvem via `tests/conftest.py:22-29` prependendo `.opencode/`. O CLI real nao passa pelo conftest, e os testes existentes em `tests/unit/query/test_main.py:43-47` ja' prependem `.opencode/` em `PYTHONPATH` manualmente — provando que o problema e' conhecido mas o workaround esta' duplicado. |
| **B8** | `UnicodeEncodeError: 'charmap' codec can't encode character '\uf0b7'` em `src/query/__main__.py:237 print(json.dumps(...))` | `python -m src.query "2025.002"` (hit de chunk com bullet `•`) | Windows PowerShell cria stdout com encoding `cp1252`; `json.dumps(..., ensure_ascii=False)` emite `\uf0b7` literal em UTF-8; `print()` tenta codificar em cp1252 e quebra. |
| **I7.1** | `[sped] erro HTTP: HTTPSConnectionPool(host='sped.gov.br', port=443): ... NameResolutionError` na coleta | `python -m src.collector --once` | `sped.gov.br` nao resolveu no DNS publico no momento da execucao (transient). Coletor exibe a mensagem crua do urllib3, sem distinguir "host nao resolve" de "timeout" ou "403". |
| **I7.2** | `(no output)` em stdout apos chamar `python -m src.query --hybrid "..."` para algumas perguntas | CLI | Hipotese: o mesmo `UnicodeEncodeError` de B8 sendo engolido (stdout fica vazio porque `print` quebrou no meio). Confirmar apos B. |
| **P7.1** | O 1o query --hybrid retornou `Nao encontrei base para responder` ("NO_EVIDENCE_MESSAGE") para "Reforma Tributaria do Consumo NF-e tags IBS CBS NT 2025.002" | CLI | Pode ser evidencia legitima (a base pode nao conter NT 2025.002 ainda) OU falha do top-k/embedding nessa consulta. Validar so' depois que A/B/D estiverem corrigidos para nao confundir encoding com semantica. |

---

## Fase A — Bootstrap automatico de sys.path para `hooks.domain_guard` (BLOQUEANTE B7)

**Criterio**: `pytest tests/unit/ tests/integration/ exit 0` **E** o comando
`python -m src.query "qualquer pergunta"` (sem mexer em `PYTHONPATH` antes) retorna JSON
com `answer` ou com `NO_EVIDENCE_MESSAGE` (sem `RuntimeError`). Workaround manual de
`PYTHONPATH` em `tests/unit/query/test_main.py:43-47` deixa de ser necessario.

### Task A.1 — Criar `src/utils/syspath_bootstrap.py` (helper compartilhado)

- Agent: Backend Engineer
- Input: nenhuma
- Diagnostico:
  - O caminho canonico de `hooks` (definido em `.opencode/hooks/domain_guard.py`) nao
    esta' no `sys.path` do Python quando o usuario roda `python -m src.<x>` direto.
  - `tests/conftest.py:22-29` ja' prepende `.opencode/` e `src/` em `sys.path`, mas a
    logica e' local e duplicada em `tests/unit/query/test_main.py:43-47`.
  - Logica canonica precisa morar em `src/`, nao em `tests/` (regra:
    `src.md` > "tipagem em src/, cobertura minima").
- Output:
  - Novo arquivo `src/utils/syspath_bootstrap.py`:
    ```python
    """Bootstrap de sys.path para permitir imports de ``.opencode/hooks/`` em CLI.

    O guardrail ``hooks.domain_guard`` vive em ``.opencode/hooks/``; testes
    pytest adicionam esse diretorio via ``tests/conftest.py``, mas entry-points
    CLI (``python -m src.<x>``) executados direto do terminal nao passam
    pelo conftest. Este helper faz a mesma adicao de forma idempotente e
    compartilhavel, sem adicionar logica nova em arquivos de teste.
    """
    from __future__ import annotations
    import sys
    from pathlib import Path

    PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
    OPENCODE_PATH: Path = PROJECT_ROOT / ".opencode"
    SRC_PATH: Path = PROJECT_ROOT / "src"

    _BOOTSTRAP_DONE: bool = False


    def ensure_sys_path() -> None:
        """Prepende ``.opencode/`` e ``src/`` em ``sys.path`` (idempotente)."""
        global _BOOTSTRAP_DONE
        if _BOOTSTRAP_DONE:
            return
        for entry in (OPENCODE_PATH, SRC_PATH):
            sp = str(entry)
            if sp not in sys.path:
                sys.path.insert(0, sp)
        _BOOTSTRAP_DONE = True


    __all__ = ["ensure_sys_path", "PROJECT_ROOT", "OPENCODE_PATH", "SRC_PATH"]
    ```
- Criterios de aceitacao:
  - [ ] Arquivo criado em `src/utils/syspath_bootstrap.py` com a tipagem completa.
  - [ ] `python -c "from src.utils.syspath_bootstrap import ensure_sys_path; ensure_sys_path(); import hooks.domain_guard; print(hooks.domain_guard.ALLOWED_DOMAINS[0])"` imprime um host oficial sem `ModuleNotFoundError`.

### Task A.2 — Chamar o bootstrap no `src/utils/http_guard.py` antes do import top-level

- Agent: Backend Engineer
- Input: A.1 criada
- Diagnostico:
  - O import `from hooks.domain_guard import ...` em `http_guard.py:38` e' top-level
    (executado no momento do `import http_guard`). Tentar envolver em `try/except`
    dentro de `install_http_guard` nao funciona: ja' levantamos `RuntimeError` antes
    de qualquer funcao ser chamada.
  - Solucao: chamar `ensure_sys_path()` no top-level de `http_guard.py` ANTES do
    import problemático. O guard e' carregado cedo o suficiente para isso nao
    quebrar call-sites lazy.
- Output:
  - `src/utils/http_guard.py` no inicio (antes do bloco `try: from hooks.domain_guard`):
    ```python
    from src.utils.syspath_bootstrap import ensure_sys_path
    ensure_sys_path()
    ```
  - Sem mudanca no `try/except` (a regra "fail-closed se hooks indisponivel"
    continua valendo — agora so' dispara se o projeto NAO estiver rodando dentro do
    repo esperado).
  - O `http_guard_bootstrap.py:31` continua importando `install_http_guard`
    normalmente; a ordem fica `ensure_sys_path -> http_guard imports hooks.domain_guard
    -> http_guard_bootstrap importa http_guard`.
- Criterios de aceitacao:
  - [ ] `git diff src/utils/http_guard.py` mostra so' as 2 linhas adicionadas.
  - [ ] `python -c "import src.utils.http_guard; print('OK')"` funciona sem `PYTHONPATH` pre-setado.
  - [ ] Suites previas (`tests/unit/test_domain_guard.py`,
    `tests/unit/test_http_guard_bootstrap.py`,
    `tests/integration/test_domain_guard_plugin.py`) continuam passando.

### Task A.3 — Refatorar `tests/conftest.py` para usar o helper compartilhado

- Agent: QA Engineer
- Input: A.1 criada
- Output:
  - `tests/conftest.py:14-29`: substituir o bloco de manipulacao de `sys.path` por:
    ```python
    from src.utils.syspath_bootstrap import ensure_sys_path
    ensure_sys_path()
    ```
    (mantendo o fixture `_ensure_hooks_on_path` em 32-43 que agora e' redundante,
    mas preservado por seguranca como no-op chamando `ensure_sys_path`).
  - Garantir idempotencia: `ensure_sys_path` tem a flag `_BOOTSTRAP_DONE`, entao
    duplo-import (conftest + helper) nao duplica entradas em `sys.path`.
- Criterios de aceitacao:
  - [ ] `git diff tests/conftest.py` mostra so' a substituicao do bloco.
  - [ ] `pytest tests/ --collect-only` nao emite nenhum warning de import.
  - [ ] Suites previas passam identicas.

### Task A.4 — Remover workaround de `PYTHONPATH` em `tests/unit/query/test_main.py`

- Agent: QA Engineer
- Input: A.1 + A.2 aplicadas
- Output:
  - `tests/unit/query/test_main.py:43-47` (que monta `env["PYTHONPATH"]` prependendo
    `.opencode/`): remover a manipulacao de `PYTHONPATH`. Manter o resto do helper
    `_run_cli` (HF_HUB_OFFLINE, OPENBLAS_NUM_THREADS, OMP_NUM_THREADS, pop COV_*).
  - Comentario atualizado: deixar nota de que o bootstrap esta' agora em
    `src/utils/syspath_bootstrap.py` invocado por `src/utils/http_guard.py`.
- Criterios de aceitacao:
  - [ ] `git diff tests/unit/query/test_main.py` mostra so' a remocao das 5 linhas de `pp_parts`.
  - [ ] `pytest tests/unit/query/test_main.py` exit 0.
  - [ ] `test_cli_with_missing_database_returns_no_evidence_message` continua passando sem o PYTHONPATH pre-setado.

### Task A.5 — Testes do helper e do bootstrap automatico

- Agent: QA Engineer
- Input: A.1 pronta
- Output:
  - `tests/unit/test_syspath_bootstrap.py` (novo, 4 testes):
    - `test_ensure_sys_path_idempotent`: chamar `ensure_sys_path()` 2x nao duplica entradas em `sys.path` (assert `sys.path.count(str(OPENCODE_PATH)) == 1`).
    - `test_ensure_sys_path_prepends_opencode_and_src`: apos chamada, ambos os paths estao no topo de `sys.path`.
    - `test_ensure_sys_path_after_bootstrap_done_no_op`: setar `_BOOTSTRAP_DONE = True` via `monkeypatch`, alterar `sys.path` removendo `OPENCODE_PATH`, chamar `ensure_sys_path()`; o path NAO e' re-adicionado (idempotencia por flag, nao por path-check) — documentar o motivo no docstring se o teste confirmar.
    - `test_ensure_sys_path_no_op_when_paths_already_present`: chamar com os paths ja' presentes (idempotente na pratica) e validar ordem preservada.
  - `tests/integration/test_cli_runs_without_pythonpath.py` (novo, 1 teste):
    - `test_query_cli_imports_without_opencode_on_path`: rodar `subprocess.run([sys.executable, "-m", "src.query", "pergunta"], cwd=tmp_path, env=os.environ.copy())` com `PYTHONPATH` reduzido a zero (`env.pop("PYTHONPATH", None)`). Espera retorno 0 e stderr/stdout sem traceback. Valida que o bootstrap de A.2 e' suficiente.
- Criterios de aceitacao:
  - [ ] Suite nova passa com `pytest tests/unit/test_syspath_bootstrap.py tests/integration/test_cli_runs_without_pythonpath.py` exit 0.
  - [ ] Cobertura de `src/utils/syspath_bootstrap.py` >= 95%.

---

## Fase B — Encoding UTF-8 no stdout do CLI query (BLOQUEANTE B8)

**Criterio**: `python -m src.query "2025.002"` (com chunk que bata retornando texto com `\uf0b7`,
emojis ou acentuacao UTF-8) imprime JSON completo no stdout **sem** levantar
`UnicodeEncodeError`. Validar via `subprocess.run(..., capture_output=True, text=True)` que
o stdout contem o JSON parseavel e o stderr nao contem traceback.

### Task B.1 — Configurar `sys.stdout` para UTF-8 no `main()` do CLI

- Agent: Backend Engineer
- Input: nenhuma
- Diagnostico:
  - `src/query/__main__.py:237` faz `print(json.dumps(response, ensure_ascii=False, indent=2))`
    direto no stdout. Em Windows PowerShell, `sys.stdout` e' `TextIOWrapper` cp1252
    por default; `json` emite UTF-8 com `ensure_ascii=False`.
  - Existem 3 abordagens:
    1. Configurar `sys.stdout.reconfigure(encoding="utf-8")` quando stdout for
       reconfiguravel (Python 3.7+ em Windows).
    2. Setar `os.environ.setdefault("PYTHONIOENCODING", "utf-8")` no inicio do CLI
       e forcar `sys.stdout` a usar UTF-8 com `io.TextIOWrapper`.
    3. (melhor de ambos) tentar reconfigure; se nao suportado, fall-back para
       reescrita do buffer.
- Output:
  - Em `src/query/__main__.py`, no topo da funcao `main()` (antes do
    `install_guard_once()` ou logo apos, nao importa a ordem):
    ```python
    def _configure_utf8_stdout() -> None:
        """Garante que sys.stdout/stderr operem em UTF-8.

        Necessario em Windows PowerShell onde o default e' cp1252;
        chunks do RAG podem conter bullets (•), emojis ou caracteres
        acentuados que quebram o encode na hora de imprimir JSON
        (`UnicodeEncodeError: 'charmap' codec can't encode character
        '\uf0b7'`).
        """
        import io
        for stream_name in ("stdout", "stderr"):
            stream = getattr(sys, stream_name, None)
            if stream is None:
                continue
            try:
                stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            except (AttributeError, ValueError):
                buf = getattr(sys, f"{stream_name}_buffer", None)
                if buf is not None:
                    setattr(sys, stream_name, io.TextIOWrapper(buf, encoding="utf-8"))
    ```
  - Chamada ` _configure_utf8_stdout()` no topo de `main()` (linhas 150-153 atuais).
  - Sem mudanca nas flags de linha de comando nem em `argparse`.
- Criterios de aceitacao:
  - [ ] `git diff src/query/__main__.py` mostra apenas o helper e a chamada adicionados.
  - [ ] Suites previas (`tests/unit/query/test_main.py`) continuam passando (capturam stdout via `text=True`, nao dependem do encoding default).

### Task B.2 — Teste de regressao com UTF-8 em stdout

- Agent: QA Engineer
- Input: B.1 aplicada
- Output:
  - Adicionar `tests/integration/test_query_cli_utf8_output.py` (novo):
    - Fixture popula `tmp_path / "storage" / "dfe.db"` com 1 chunk cujo `content`
      contem uma string com bullet `•`, emoji `🟢` e `ç`/`ã`.
    - Subprocess: `python -m src.query "pergunta qualquer"` em `cwd=tmp_path`, com
      `PYTHONPATH` reduzido (ja' coberto pelo bootstrap da Fase A) mas `PYTHONIOENCODING`
      nao setada (deixa o default Windows agir — o helper da Fase B e' que precisa corrigir).
    - Asserts: `result.returncode == 0`, `result.stdout` parseado como JSON contem
      `answer` (string ou `NO_EVIDENCE_MESSAGE`), `result.stderr` nao contem
      `'UnicodeEncodeError'`.
  - Documentar no docstring do teste o por que do nome (regressao de B.1).
- Criterios de aceitacao:
  - [ ] Antes de B.1: teste falha com `UnicodeEncodeError` no stderr (vermelho).
  - [ ] Depois de B.1: teste passa (verde).
  - [ ] `pytest tests/integration/test_query_cli_utf8_output.py` exit 0.

---

## Fase C — Diagnostico amigavel para erros de rede no coletor (IMPORTANTE I7.1)

**Criterio**: `python -m src.collector --diagnose-net` produz JSON listando cada host
em `ALLOWED_DOMAINS` com `{host, resolves, reachable, error?}`. A saida e' legivel
para humanos e para maquinas (orquestrador externo). Quando a coleta `--once` falha
para todos os hosts, o erro reportado indica o motivo canonico (NXDOMAIN, timeout,
403) por host.

### Task C.1 — Flag `--diagnose-net` em `src/collector/__main__.py`

- Agent: Backend Engineer
- Input: nenhuma
- Output:
  - `src/collector/__main__.py`: adicionar `--diagnose-net` ao argparse. Quando
    presente, NAO chama `DocumentCollector.discover_and_register`; em vez disso,
    itera `ALLOWED_DOMAINS` (importavel de `hooks.allowed_domains` ou do guard) e
    para cada host tenta: (a) `socket.getaddrinfo(host, 443)` (DNS), (b) `requests.get`
    com `timeout=5` na raiz do host. Reporta JSON por stdout.
  - Reusar `safe_session_get` (ja' disponivel em `src/utils/http_guard.py`) para
    o probe HTTP — o guard ja' filtra hosts nao permitidos, mas aqui so' vamos
    iterar hosts oficiais, entao o filtro passa.
  - Exit code: 0 se todos OK, 1 se algum falhou (util para CI/script).
- Criterios de aceitacao:
  - [ ] Implementado sem novas dependencias externas (apenas stdlib + requests ja' em uso).
  - [ ] Doctring explicando que o probe e' nao-intrusivo (HEAD/GET em raiz, timeout=5s).

### Task C.2 — Tratamento de erro de rede em `discover_and_register`

- Agent: Backend Engineer
- Input: C.1 implementada
- Output:
  - `src/collector/downloader.py` (ou onde `discover_and_register` estiver) — capturar
    `requests.exceptions.RequestException` e capturar o sub-tipo (`ConnectionError`,
    `Timeout`, `HTTPError`). Logar uma linha por host com:
    `[<portal>] erro: <motivo canonico> (<classe urllib3>) — host=<hostname>`.
  - Quando TODOS os hosts falharem, emitir mensagem adicional sugerindo
    `python -m src.collector --diagnose-net` para o usuario.
  - Manter comportamento fail-closed: qualquer excecao em rede NAO faz o coletor
    prosseguir sem diagnostico. O guardrail (`AGENTS.md > Nunca fazer > nunca
    metralhar`) ja' e' respeitado.
- Criterios de aceitacao:
  - [ ] Suite previa de coletor continua passando.
  - [ ] Novo teste em `tests/unit/collector/test_diagnose_net.py`:
    `test_discover_categorizes_connection_error_per_host` (mocka
    `requests.Session().get` levantando `ConnectionError`; asserta mensagem por
    host, nao traceback cru).
  - [ ] Cobertura de `src/collector/downloader.py` permanece >= 95%.

### Task C.3 — Testes do `--diagnose-net` (subprocess end-to-end)

- Agent: QA Engineer
- Input: C.1 + C.2 aplicadas
- Output:
  - `tests/integration/test_collector_diagnose_net.py` (novo, 2 testes):
    - `test_diagnose_net_reports_all_allowed_hosts`: itera `ALLOWED_DOMAINS` real
      (sem rede para hosts nao permitidos; aceita-se que hosts reais podem mudar
      de estado — usamos um patch que valida apenas a estrutura do JSON).
    - `test_diagnose_net_exits_nonzero_when_a_host_fails`: monkeypatchar 1 host
      para levantar `ConnectionError`, validar exit code 1 e JSON marcando aquele
      host como `reachable=false`.
- Criterios de aceitacao:
  - [ ] Suite nova passa sem acesso real a rede (mocks via `monkeypatch`).
  - [ ] Garante que `--diagnose-net` e' seguro para rodar em CI.

---

## Fase D — Cleanup do sintoma "no output" em queries hibridas (IMPORTANTE I7.2)

**Criterio**: apos A+B aplicadas, a hipotese de que `(no output)` era o mesmo
`UnicodeEncodeError` de B8 engolido e' validada ou refutada: existe teste que
documenta o caminho. Se validado, I7.2 fica resolvido de tabela como efeito colateral
de B; se refutado, e' levantado como novo BLOQUEANTE em Sprint 8.

### Task D.1 — Reproducao controlada do "(no output)"

- Agent: QA Engineer
- Input: A + B aplicadas
- Output:
  - Adicionar `tests/integration/test_query_hybrid_no_silent_failure.py` (novo):
    - Capturar stdout via `subprocess.run(..., capture_output=True, text=True,
      cwd=tmp_path)`.
    - Inserir um chunk com conteudo que quebra cp1252 (ex.: `\uf0b7`).
    - Rodar `python -m src.query --hybrid "<pergunta com termo literal>"`
      apontando para o chunk.
    - Asserts: `result.returncode in (0, 1)` (nao segmentfault), `result.stdout`
      comeca com `{` (JSON valido), `result.stderr` nao contem `UnicodeEncodeError`.
  - Se o teste passa: I7.2 estava mesmo em B; documenta como tal no docstring e
    move para "resolvido por B8".
  - Se o teste falha com outro padrao: e' novo BLOQUEANTE; registrar em Sprint 8.
- Criterios de aceitacao:
  - [ ] Suite nova passa **ou** falhas sao registradas como issues para Sprint 8.

### Task D.2 — Log estruturado de "sem hits" no `QueryEngine`

- Agent: Backend Engineer
- Input: D.1 executada
- Output:
  - Garantir que quando `QueryEngine.search` retorna lista vazia, o `_build_answer`
    em `src/query/__main__.py` registra log em stderr (uma linha: `[query] sem
    chunks relevantes — topicos: <len>`) ANTES de emitir o JSON do NO_EVIDENCE_MESSAGE.
  - Justificativa: evita que o usuario veja um JSON vazio e pense que o sistema
    travou (o mesmo padrao causou o "(no output)" reportado).
  - Mudanca minima: `print("sem chunks relevantes", file=sys.stderr)` em
    `src/query/__main__.py` na rotina `_build_answer` quando `ranked` e' vazio.
- Criterios de aceitacao:
  - [ ] Cobertura de `src/query/__main__.py::main` continua >= 80%.
  - [ ] Teste em `tests/unit/query/test_main.py`: asserir `result.stderr` contem
    `"sem chunks relevantes"` em caso de base vazia.

---

## Fase E — Documentacao e finalizacao (PARCIAL P7.1)

### Task E.1 — Atualizar `AGENTS.md` com decisoes Sprint 7

- Agent: Backend Engineer
- Output:
  - Adicionar bloco `## Decisoes resolvidas (Sprint 7)` ao final da secao de
    decisoes resolvidas em `AGENTS.md`, com as 4 decisoes principais:
    1. `src/utils/syspath_bootstrap.ensure_sys_path()` e' a fonte canonica de bootstrap
       de sys.path para entry-points CLI; testes (conftest) e CLI real passam pelo mesmo
       helper; o workaround manual de `PYTHONPATH` em `tests/unit/query/test_main.py`
       foi REMOVIDO.
    2. `src/query/__main__.py::_configure_utf8_stdout()` reescreve stdout/stderr para
       UTF-8 antes de imprimir JSON; UTF-8 e' default em Linux/Mac, e em Windows
       PowerShell o codigo cobre a lacuna (`UnicodeEncodeError: cp1252 \uf0b7`).
    3. `--diagnose-net` em `src/collector/__main__.py` e' a porta de entrada canonica
       para investigar indisponibilidade de hosts (NXDOMAIN, timeout, 403).
    4. Quando query nao tem hits, `src/query/__main__.py` escreve linha em stderr
       para nao confundir "sem chunks" com "travou".

### Task E.2 — Atualizar `scripts/check_env.ps1` para detectar sys.path quebrado

- Agent: Backend Engineer
- Output:
  - Adicionar 6o escopo de validacao: "python -c 'from src.utils import http_guard; print(\"OK\")'"
    exit 0? Se exit != 0, `import_ok: false` no JSON final, com `recommendation` apontando
    para o runbook de A (re-instalar dependencias ou rodar `python -m pip install -e .`).
  - Manter `check_env.ps1` idempotente (ja' documentado no header).

### Task E.3 — Marcar este plano como concluido

- Agent: Backend Engineer
- Output:
  - `PLAN_SPRINT7.md` re-apresentado em `AGENTS.md > Decisoes resolvidas (Sprint 7)`
    na forma de resumo (4 decisoes).
  - Apêndice B (fora de escopo) movido para `PLAN_SPRINT8.md` se houver itens.

---

## Verificacao manual dos BLOQUEANTE

Comandos shell a serem executados **apos** A e B concluidas. DEVEM ser executados a
partir de um PowerShell "fresco" (sem `$env:PYTHONPATH` pre-setado):

```powershell
# BLOQUEANTE B7: CLI carrega sem mexer em PYTHONPATH
$env:PYTHONPATH = $null  # garante que nao ha workaround
python -m src.query "como cancelar NF-e apos a NT 2025.002"
# esperado: JSON no stdout com `answer` ou `Nao encontrei base para responder`.
# proibido: traceback "RuntimeError: domain_guard indisponivel"

# BLOQUEANTE B8: stdout em UTF-8 mesmo com bullet na resposta
$env:PYTHONIOENCODING = $null  # garante que nao ha workaround
python -m src.query "2025.002" | Out-File -Encoding utf8 "$env:TEMP\s7_b8.json"
Get-Content "$env:TEMP\s7_b8.json"
# esperado: JSON completo, sem traceback, sem caracteres corrompidos.
# proibido: "UnicodeEncodeError: 'charmap' codec can't encode character '\uf0b7'"
```

Cobrindo tambem I7.1 (sintoma colateral):

```powershell
# Diagnostico de rede: lista todos os hosts oficiais com status
python -m src.collector --diagnose-net | Out-File -Encoding utf8 "$env:TEMP\s7_diag.json"
Get-Content "$env:TEMP\s7_diag.json"
# esperado: JSON com cada host de ALLOWED_DOMAINS e o campo `resolves`/`reachable`.
# se algum host falhou: exit code 1; o JSON marca `reachable: false` + `error: <motivo>`.
```

---

## Apêndice A — Riscos conhecidos e mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| A.2 inserir `ensure_sys_path()` no top-level quebra import ciclico se `http_guard` for importado por `syspath_bootstrap` (ou vice-versa) | Baixa | Alto | `syspath_bootstrap` NAO importa `http_guard`; `http_guard` importa `syspath_bootstrap` (sem dependencia de volta). Validado na ordem de imports do projeto (CLI -> bootstrap -> http_guard -> guard). |
| A.4 quebrar testes que monkeypatcham `PYTHONPATH` deliberadamente | Baixa | Baixo | Verificado que `_run_cli` em `tests/unit/query/test_main.py:43` nao e' reusado por outros testes; suite continua passando. |
| B.1 `sys.stdout.reconfigure()` nao existe em Python <3.7 ou em streams redirecionados (subprocess com `text=False`) | Media | Baixo | Fallback via `io.TextIOWrapper(sys.stdout_buffer, encoding="utf-8")` no bloco `except (AttributeError, ValueError)`. |
| B.2 teste com chunk "quebra-cp1252" pode ser flaky se encoding default do harness mudar | Baixa | Baixo | Teste usa `text=False` (binario) para ler os bytes crus do stdout e decodifica com UTF-8 explicitamente — independe do encoding default do PowerShell. |
| C.1 `--diagnose-net` ser usado para "metralhar" hosts (Tyrrell-noisy probes) | Baixa | Medio | Probe usa `HEAD` em raiz + timeout=5s; documenta no help text que NAO e' para controle de uptime. Limitar a 1 chamada por host (sem retry). |
| D.1 hipotese de B ser responsavel por D ser falsa (causa diferente, ex.: FTS5 query malformada) | Media | Medio | Tentar reproduzir primeiro sem o `_configure_utf8_stdout` aplicado; se o traceback for diferente do B8, I7.2 vira BLOQUEANTE novo (Sprint 8). |
| Usar `unicode` puro no JSON (com `ensure_ascii=False`) ainda depender do stdout para encoding final | Baixa | Baixo | Garantido pelo reconfigure de B.1; cobrimos tambem stderr para logs de queries sem hits (B.1 reconfigure ambos). |

## Apêndice B — Itens fora do escopo desta Sprint (follow-up)

1. **Conteudo da base sobre RTC NF-e (NT 2025.002, tags UB/grupo W03/IBSCBS)** — so'
   faz sentido apos A+B+collector funcionando; quando esta Sprint estiver concluida,
   rodar `python -m src.collector --once` em horario com DNS `sped.gov.br` saudavel
   para fazer o ingest dos docs RTC faltantes, e depois `python -m src.ragctl benchmark`
   para medir recall.
2. **Substituir `chr(149)` (bullet) no extrator de PDF** por `'\u2022'` antes da
   indexacao — evita que o RAG guarde `\uf0b7` que e' "PRIVATE USE AREA" (U+E000-U+F8FF)
   e raramente faz sentido em texto fiscal. Sugestao para Sprint 8 (parser).
3. **Mover `_run_cli` de `tests/unit/query/test_main.py` para `tests/utils/cli_runner.py`**
   — compartilhar entre suites de teste de entry-points. Nao bloqueia agora (so' ha'
   1 consumidor).
4. **Implementar `--diagnose-net` como health-check HTTP** se algum dia o agente
   expor um endpoint (hoje NAO ha' API HTTP, ver `src.md > sem API HTTP`). Manter
   apenas CLI.
5. A pergunta original do usuario (manipular tags NFC-e/NF-e de notas de credito e
   debito no `RtcXmlBuilder.vb` externo ao workspace) — fora do escopo do DFe-Agent.
   Este agente consulta a base RAG para fundamentar; a **manipulacao do .vb** em si
   e' trabalho de engenharia VB no projeto Gestplus, nao desta ferramenta.

---

## Apêndice C — Resumo de comandos para reproduzir localmente

```powershell
# 0. Ambiente
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 1. Verificar ambiente (inclui novo check de imports de http_guard)
pwsh scripts/check_env.ps1

# 2. Validar que BLOQUEANTE B7 esta resolvido
$env:PYTHONPATH = $null
python -m src.query "hello"
# esperado: JSON com NO_EVIDENCE_MESSAGE (base pode estar vazia) SEM traceback

# 3. Validar que BLOQUEANTE B8 esta resolvido
python -m src.query "2025.002" | Out-File -Encoding utf8 out.json
Get-Content out.json

# 4. Coletar e indexar base (gate para conteudo da Sprint 8)
python -m src.collector --once
python -m src.indexer.ingest

# 5. Sanidade final
pytest tests/ --cov=src --cov-fail-under=80
```
