"""Gate anti-regressao da unificacao do harness em ``.opencode/`` (PLAN_SPRINT12 B12.1, Task 7.1).

Consolida os gates que bloqueiam qualquer regressao futura do layout
``.claude/`` vs ``.opencode/``. Cobre:

- ``.claude/`` nao existe mais no projeto (removido na Fase 5).
- Nenhum path canonico ``.claude/(agents|hooks|rules|skills|scripts|state|
  knowledge|storage|rag.db|schema.sql)`` aparece em codigo-fonte ativo
  (``.opencode/``, ``opencode.json``).
- 5 hooks scripts (3 dev + 2 code-reviewer) vivem em ``.opencode/hooks/``.
- 5 scripts TS do RAG meta vivem em ``.opencode/rag/`` + 4 lib em
  ``.opencode/rag/lib/``.
- 5 rules vivem em ``.opencode/rules/`` (4 migradas + 1 nativa).
- Plugin TS aponta para os novos paths ``.opencode/hooks/...`` em 5 sites.

Tolerancias:
- ``.opencode/rag/knowledge/<date>-*.md`` (artefatos historicos do RAG
  meta-cognitivo que citam paths antigos como exemplo: 4 arquivos).
- ``__pycache__/`` (bytecode Python gerado em runtime).
- ``AGENTS.md`` pode conter notas historicas de Sprints passadas em
  blocos ``## Decisoes resolvidas (Sprint N)``; notas didaticas sobre a
  transicao ``.claude/`` -> ``.opencode/`` sao permitidas. Testes
  cobrem apenas o estado canonico ATIVO.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Cenario 1: .claude/ nao existe mais
# ---------------------------------------------------------------------------


def test_no_dot_claude_dir_exists() -> None:
    """Diretorio ``.claude/`` deve ter sido removido (Fase 5)."""
    claude_dir = PROJECT_ROOT / ".claude"
    assert not claude_dir.exists(), (
        f"{claude_dir} NAO deve existir (unificacao Sprint 12 completa). "
        f"Conteudo: {list(claude_dir.iterdir()) if claude_dir.exists() else 'N/A'}"
    )


# ---------------------------------------------------------------------------
# Cenario 2: codigo-fonte canonico nao cita paths .claude/<subpath>
# ---------------------------------------------------------------------------


def _scan_claude_paths_in_files(patterns: tuple[str, ...]) -> list[tuple[Path, int, str]]:
    """Procura references a paths ``.claude/<subpath>`` em arquivos canonicos.

    Tolera:
    - ``.opencode/rag/knowledge/<date>-*.md`` (artefatos historicos do RAG).
    - ``__pycache__/`` (bytecode Python gerado em runtime).
    - Diretorios nao-canonicos (``.claude/..`` ou outros).

    Args:
        patterns: tupla de regex patterns a procurar.

    Returns:
        Lista de tuplas ``(path, line_number, line_text)`` com matches.
    """
    hits: list[tuple[Path, int, str]] = []
    forbidden_dirs = {"__pycache__", "node_modules"}
    # Percorre recursivamente apenas arquivos de codigo-fonte e configs
    root = PROJECT_ROOT
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in forbidden_dirs for part in rel.parts):
            continue
        # Tolera artefatos historicos do RAG (knowledge/*.md).
        if (
            rel.parts[:3] == (".opencode", "rag", "knowledge")
            and rel.suffix == ".md"
        ):
            continue
        # AGENTS.md: notas historicas em `## Decisoes resolvidas (Sprint N)`
        # sao permitidas (test_AGENTS_md_no_active_claude_paths cobre o resto).
        if path.name == "AGENTS.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pat in patterns:
                if re.search(pat, line):
                    hits.append((path, lineno, line.strip()))
    return hits


_CLAUDE_PATH_PATTERNS: tuple[str, ...] = (
    r"\.claude/(agents|hooks|rules|skills|scripts|state|knowledge|storage|rag\.db|schema\.sql)",
)


@pytest.mark.parametrize(
    "path_glob",
    [".opencode/**/*.md", ".opencode/**/*.py", ".opencode/**/*.ts", "opencode.json"],
    ids=["md", "py", "ts", "json"],
)
def test_no_dot_claude_in_opencode_subtree(path_glob: str) -> None:
    """Nenhum arquivo canonico em ``.opencode/`` cita ``.claude/<subpath>``.

    Exclui artefatos historicos ``.opencode/rag/knowledge/<date>-*.md``
    e bytecode Python ``__pycache__/``.
    """
    hits = _scan_claude_paths_in_files(_CLAUDE_PATH_PATTERNS)
    relevant = [
        (p, ln, txt)
        for (p, ln, txt) in hits
        if any(p.match(glob_str) for glob_str in [
            str(PROJECT_ROOT / ".opencode") + sep + "**" + sep + "*"
            for sep in ["/", "\\"]
        ])
        or p.name == "opencode.json"
    ]
    assert not relevant, (
        f"Encontradas {len(relevant)} referencias a paths `.claude/<subpath>` "
        f"em codigo canonico (Sprint 12 B12.1 - 12.5): "
        + "\n".join(f"  {p}:{ln}: {txt}" for p, ln, txt in relevant[:10])
    )


# ---------------------------------------------------------------------------
# Cenario 3: estrutura canonica dos diretorios
# ---------------------------------------------------------------------------


def test_opencode_hooks_has_required_scripts() -> None:
    """``.opencode/hooks/`` tem 5 scripts (3 dev + 2 code-reviewer) + 3 lib."""
    hooks_dev = PROJECT_ROOT / ".opencode" / "hooks" / "dev"
    hooks_cr = PROJECT_ROOT / ".opencode" / "hooks" / "code-reviewer"
    hooks_lib = PROJECT_ROOT / ".opencode" / "hooks" / "_lib"
    for script in ("pre_tool_use.py", "post_tool_use.py", "stop.py"):
        assert (hooks_dev / script).is_file(), (
            f".opencode/hooks/dev/{script} deve existir"
        )
    for script in ("pre_tool_use.py", "pre_tool_use_bash.py"):
        assert (hooks_cr / script).is_file(), (
            f".opencode/hooks/code-reviewer/{script} deve existir"
        )
    for mod in ("learning.py", "payload.py", "test_runner.py"):
        assert (hooks_lib / mod).is_file(), (
            f".opencode/hooks/_lib/{mod} deve existir"
        )


def test_opencode_rag_has_5_scripts_and_4_lib() -> None:
    """``.opencode/rag/`` tem 5 scripts + 4 lib."""
    rag_dir = PROJECT_ROOT / ".opencode" / "rag"
    for script in ("init_db.ts", "summarize.ts", "embed.ts", "search.ts", "smoke_test.ts"):
        assert (rag_dir / script).is_file(), (
            f".opencode/rag/{script} deve existir"
        )
    lib_dir = rag_dir / "lib"
    for lib_script in ("db.ts", "chunker.ts", "embedder.ts", "classifier.ts"):
        assert (lib_dir / lib_script).is_file(), (
            f".opencode/rag/lib/{lib_script} deve existir"
        )


def test_opencode_rules_count_is_5() -> None:
    """``.opencode/rules/`` tem 5 rules (4 migradas + 1 nativa)."""
    rules_dir = PROJECT_ROOT / ".opencode" / "rules"
    md_files = {p.stem for p in rules_dir.glob("*.md") if p.stem != "README"}
    expected = {"seguranca", "convencoes-gerais", "src", "tests", "dfe-rules"}
    assert md_files == expected, (
        f".opencode/rules/ deve ter 5 rules canonicas {expected}; "
        f"obtido {md_files}"
    )


# ---------------------------------------------------------------------------
# Cenario 4: plugin TS aponta para os novos paths
# ---------------------------------------------------------------------------


def _read_plugin_ts() -> str:
    return (PROJECT_ROOT / ".opencode" / "plugin" / "agent-hooks.ts").read_text(
        encoding="utf-8"
    )


def test_plugin_ts_points_to_opencode_hooks() -> None:
    """Plugin TS tem 5 paths hardcoded apontando para ``.opencode/hooks/``."""
    src = _read_plugin_ts()
    opencode_paths = re.findall(r"\.opencode/hooks/[^\"'\s]+", src)
    assert len(opencode_paths) >= 5, (
        f"agent-hooks.ts deveria apontar para 5 paths `.opencode/hooks/...` "
        f"(preToolUse, preToolUseBash, postToolUse, stop + variations); "
        f"obtido {len(opencode_paths)}: {opencode_paths}"
    )
    assert not re.search(r"\.claude/hooks/", src), (
        "agent-hooks.ts NAO deve apontar para `.claude/hooks/` "
        "(Sprint 12 B12.1)"
    )


# ---------------------------------------------------------------------------
# Cenario 5: helper learning.py aponta para .opencode/rag/
# ---------------------------------------------------------------------------


def test_learning_helper_paths_use_opencode_rag() -> None:
    """``_lib/learning.py::KNOWLEDGE_DIR`` e ``SCRIPTS_DIR`` apontam para ``.opencode/rag/``."""
    import importlib.util
    script = PROJECT_ROOT / ".opencode" / "hooks" / "_lib" / "learning.py"
    spec = importlib.util.spec_from_file_location("learning_for_unified", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    expected_knowledge = mod.PROJECT_ROOT / ".opencode" / "rag" / "knowledge"
    expected_scripts = mod.PROJECT_ROOT / ".opencode" / "rag"
    assert mod.KNOWLEDGE_DIR == expected_knowledge, (
        f"KNOWLEDGE_DIR={mod.KNOWLEDGE_DIR} deve ser igual a "
        f"{expected_knowledge}"
    )
    assert mod.SCRIPTS_DIR == expected_scripts, (
        f"SCRIPTS_DIR={mod.SCRIPTS_DIR} deve ser igual a {expected_scripts}"
    )


# ---------------------------------------------------------------------------
# Cenario 6: init_db.ts roda no novo path
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="smoke test init_db.ts requer Windows shell + node_modules",
)
def test_opencode_init_db_creates_db_in_opencode_rag() -> None:
    """``npx tsx .opencode/rag/init_db.ts`` cria ``.opencode/rag/rag.db``.

    Requer ``.opencode/node_modules/`` instalado (skip se ausente).
    """
    tsx_bin = PROJECT_ROOT / ".opencode" / "node_modules" / ".bin" / "tsx.cmd"
    if not tsx_bin.exists():
        pytest.skip("`.opencode/node_modules/.bin/tsx.cmd` nao instalado")
    init_ts = PROJECT_ROOT / ".opencode" / "rag" / "init_db.ts"
    if not init_ts.exists():
        pytest.skip(f"{init_ts} nao existe (smoke nao aplicavel)")
    proc = subprocess.run(
        [str(tsx_bin), str(init_ts.relative_to(PROJECT_ROOT))],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"init_db.ts falhou: rc={proc.returncode} stderr={proc.stderr!r}"
    )
    rag_db = PROJECT_ROOT / ".opencode" / "rag" / "rag.db"
    assert rag_db.exists(), (
        f"{rag_db} deve ter sido criado por init_db.ts "
        f"(Sprint 12 B12.4 unificacao)"
    )


# ---------------------------------------------------------------------------
# Cenario 7: gate de documentacao canonica AGENTS.md tem bloco Sprint 12
# ---------------------------------------------------------------------------


def test_AGENTS_md_has_sprint12_decisions_block() -> None:
    """AGENTS.md deve ter bloco ``## Decisões resolvidas (Sprint 12)``."""
    agents_md = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Decisões resolvidas (Sprint 12)" in agents_md, (
        "AGENTS.md deve conter bloco `## Decisões resolvidas (Sprint 12)` "
        "sumarizando as 6-8 decisoes principais + paths de evidencia"
    )
    assert "B12.1" in agents_md, (
        "AGENTS.md bloco Sprint 12 deve referenciar B12.1 (unificacao hooks)"
    )
    assert "B12.4" in agents_md, (
        "AGENTS.md bloco Sprint 12 deve referenciar B12.4 (unificacao RAG meta)"
    )


def test_AGENTS_md_no_active_claude_paths() -> None:
    """AGENTS.md NAO cita ``.claude/<subpath>`` fora dos blocos ``Decisoes resolvidas (Sprint N)``.

    Notas historicas (Sprints 1-11) sao permitidas em ``## Decisoes
    resolvidas (Sprint N)`` para documentar a evolucao do projeto;
    mas texto canonico ATIVO (cabelhos de secao, comandos, paths)
    deve apontar para ``.opencode/``.

    Anti-regressao: se um dev futuro adicionar ``.claude/<subpath>``
    num contexto nao-historico, o teste falha.
    """
    agents_md = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    pattern = re.compile(
        r"\.claude/(agents|hooks|rules|skills|scripts|state|knowledge|storage|rag\.db|schema\.sql)"
    )
    # Estrategia: extrai todos os blocos `## Decisoes resolvidas (Sprint N)`
    # (podem aparecer em qualquer ordem no arquivo). Linhas dentro desses
    # blocos sao historicas; resto e' texto ativo.
    lines = agents_md.splitlines()
    active_lines: list[str] = []
    skip_until_next_h2 = False
    for line in lines:
        # Normaliza encoding: aceita "Decisoes" (ASCII) e "Decisões" (UTF-8)
        # para tolerar ambas as variantes presentes no AGENTS.md atual.
        normalized = line.replace("õ", "o").replace("ç", "c")
        if normalized.startswith("## Decisoes resolvidas (Sprint"):
            skip_until_next_h2 = True
            continue
        if normalized.startswith("## ") and skip_until_next_h2:
            skip_until_next_h2 = False
        if not skip_until_next_h2:
            active_lines.append(line)
    active_text = "\n".join(active_lines)
    hits = pattern.findall(active_text)
    assert not hits, (
        f"AGENTS.md tem {len(hits)} referencias a `.claude/<subpath>` em "
        f"secoes ATIVAS (fora de blocos historicos `Decisoes resolvidas`). "
        f"Padrao: use `.opencode/<subpath>` para paths canonicos ativos."
    )


# ---------------------------------------------------------------------------
# Cenario 8: knowledge unificado (Sprint 13 I13.2)
# ---------------------------------------------------------------------------


def test_rag_knowledge_no_legacy_slugs() -> None:
    """Nenhum arquivo em ``.opencode/rag/knowledge/`` usa slug de agent removido.

    Agents removidos em Sprint 11 (backend-engineer, ml-engineer,
    prompt-engineer, qa-engineer) NAO devem aparecer em filenames
    de knowledge (pattern: ``<YYYY-MM-DD>-<slug>.md`` ou
    ``<YYYY-MM-DD>-<slug>-<contexto>.md``).

    Sprint 13 I13.2 canonicalizou o legado de 2026-08-25 (renomeado
    ``2026-08-25-backend-engineer.md`` -> ``2026-08-25-dev.md``).
    Anti-regressao: se um hook futuro gerar .md com slug legacy,
    este teste falha.
    """
    knowledge_dir = PROJECT_ROOT / ".opencode" / "rag" / "knowledge"
    legacy_slugs = {
        "backend-engineer",
        "ml-engineer",
        "prompt-engineer",
        "qa-engineer",
        "build",
        "plan",
    }
    offenders: list[str] = []
    for path in knowledge_dir.glob("*.md"):
        stem = path.stem
        # Filename esperado: <YYYY-MM-DD>-<slug>.md ou
        # <YYYY-MM-DD>-<slug>-<contexto>.md
        # parts = [YYYY, MM, DD, slug, ...]
        parts = stem.split("-", 3)
        if len(parts) < 4:
            continue
        slug = parts[3]
        if slug in legacy_slugs:
            offenders.append(path.name)
    assert not offenders, (
        f"Knowledge dir tem arquivos com slugs legacy (Sprint 11 I11.2): "
        f"{offenders}. Padrao canonico: use slug de agent ativo "
        f"(`dev`, `code-reviewer`, `session`) ou slug contextual "
        f"(`feature-*`, `bug-*`, `sprint-*`)."
    )