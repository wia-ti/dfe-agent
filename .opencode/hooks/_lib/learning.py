"""Helper para captura de aprendizados a partir dos hooks ``stop.py`` (PLAN_SPRINT8 B.2 + Sprint 11).

Este modulo expoe a logica canonica de ``summarize.ts -> embed.ts`` para os
hooks ``stop.py`` (canonico: ``.opencode/hooks/dev/stop.py`` desde Sprint 10).
A centralizacao aqui permite:

- DRY entre o hook ``dev/stop.py`` e o hook ``code-reviewer/stop.py``
  (Sprint 10 manteve a centralizacao apos reduzir agents de 6 para 2).
- Idempotencia composta por ``(agent_slug, session_id)`` (NAO colapsar 2
  sessoes do mesmo agent em 1 entrada so').
- Fire-and-forget via ``subprocess.Popen detached`` para NAO bloquear o
  encerramento do agent (o embed do modelo ONNX pode levar varios minutos
  no primeiro download).

> **Sprint 11 B11.1**: ``PROJECT_ROOT`` foi corrigido de ``parents[2]``
> para ``parents[3]`` (mesma profundidade que ``_lib/payload.py``). Bug
> pre-Sprint 11 produzia artefatos em paths errados (diretorio aninhado
> ``.<harness>/.<harness>/knowledge/`` e ``.<harness>/storage/agent_hooks.log``;
> o ``<harness>`` legado era ``.claude`` ate Sprint 12). Gate
> ``test_learning_helper.py::test_project_root_resolves_to_dfe_agent_root``
> protege o fix.
>
> **Sprint 12 (B12.1)**: diretorios migraram para ``.opencode/hooks/``;
> ``KNOWLEDGE_DIR`` e ``SCRIPTS_DIR`` migraram para
> ``.opencode/rag/{knowledge,}``. ``PROJECT_ROOT`` continua valido
> (mesma profundidade 3 niveis).

Funcoes publicas:

- :func:`marker_path` retorna o path do marker de idempotencia
  ``_pending-<safe>-<safe>.md.lock`` em ``.opencode/rag/knowledge/``.
- :func:`should_record` retorna ``False`` se o marker existe (idempotente).
- :func:`spawn_summarize_then_embed` orquestra summarize+embed async a
  partir de um transcript path. Retorna sempre 0 (fire-and-forget).

Caracteristicas (PLAN_SPRINT8 B.5):

- Marker composto ``(agent_slug, session_id)`` — evita colisao entre
  sessoes do mesmo agent.
- Marker criado apenas apos summarize bem-sucedido.
- Transcript ausente: skip silencioso (NAO falha).
- summarize rc != 0: skip silencioso (NAO spawn embed).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
KNOWLEDGE_DIR: Path = PROJECT_ROOT / ".opencode" / "rag" / "knowledge"
LOG_PATH: Path = PROJECT_ROOT / "storage" / "agent_hooks.log"
SCRIPTS_DIR: Path = PROJECT_ROOT / ".opencode" / "rag"
TSX_BIN: str = "npx.cmd" if sys.platform == "win32" else "npx"


def _knowledge_dir() -> Path:
    """Resolve ``.opencode/rag/knowledge`` relativo ao PROJECT_ROOT atual.

    Computado em tempo de chamada (NAO em tempo de import) para que
    testes que monkeypatchem ``PROJECT_ROOT`` tambem redirecionem o
    diretorio de conhecimento. Idempotente.
    """
    return PROJECT_ROOT / ".opencode" / "rag" / "knowledge"

_SAFE_RE: re.Pattern[str] = re.compile(r"[^A-Za-z0-9_-]+")


def _safe_slug(value: str, fallback: str) -> str:
    """Saniza ``value`` para uso em filename; vazio -> ``fallback``."""
    cleaned = _SAFE_RE.sub("-", str(value or "")).strip("-")
    return cleaned or fallback


def marker_path(agent_slug: str, session_id: str) -> Path:
    """Path do marker de idempotencia composto ``(agent_slug, session_id)``.

    Formato canonico: ``_pending-<safe-agent>-<safe-session>.md.lock`` em
    ``.opencode/rag/knowledge/``.

    Args:
        agent_slug: slug do agent (ex.: ``"backend-engineer"``).
        session_id: id da sessao do opencode (ex.: ``"01HQRS..."``).

    Returns:
        Path absoluto para o arquivo de marker.
    """
    safe_agent = _safe_slug(agent_slug, "agent")
    safe_session = _safe_slug(session_id, "session")
    return _knowledge_dir() / f"_pending-{safe_agent}-{safe_session}.md.lock"


def should_record(agent_slug: str, session_id: str) -> bool:
    """Retorna ``True`` se ainda NAO ha marker (deve gravar)."""
    return not marker_path(agent_slug, session_id).exists()


def payload_has_edits(payload: dict) -> bool:
    """True se payload tem ``tool_writes_count > 0`` (escopo = so' impl).

    Usado pelos ``stop.py`` para gate de escopo: sessoes sem edicoes
    (apenas leitura, ou dry-runs) NAO devem poluir o RAG meta-cognitivo.

    Args:
        payload: dict JSON recebido do plugin TS no stop event.

    Returns:
        True apenas se ``tool_writes_count`` for ``int > 0``. Qualquer
        outro tipo (None, str, list) retorna False (escopo defensivo).
    """
    value = payload.get("tool_writes_count")
    return isinstance(value, int) and value > 0


def resolve_transcript(payload: dict) -> Path | None:
    """Resolve path do transcript a partir do payload.

    Ordem de precedencia:

    1. Campo explicito ``transcript_path`` no payload (preferido quando
       o plugin TS grava transcript por sessao).
    2. ``.opencode/sessions/<session_id>.jsonl`` se session_id fornecido.
    3. ``.opencode/sessions/<mtime-recente>.jsonl`` (ultimo recurso).

    Args:
        payload: dict JSON com campos opcionais ``transcript_path`` e
            ``session_id``.

    Returns:
        Path para o transcript, ou None se nenhum candidato existe.
    """
    explicit = payload.get("transcript_path")
    if explicit:
        path = Path(str(explicit))
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if path.exists():
            return path

    session_id = str(payload.get("session_id") or "").strip()
    if session_id:
        candidate = PROJECT_ROOT / ".opencode" / "sessions" / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate

    sessions_dir = PROJECT_ROOT / ".opencode" / "sessions"
    if sessions_dir.is_dir():
        candidates = sorted(
            sessions_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]

    return None


def _md_path(agent_slug: str, session_id: str) -> Path:
    """Path do ``.md`` intermediario (mesmo nome do marker, extensao ``.md``)."""
    safe_agent = _safe_slug(agent_slug, "agent")
    safe_session = _safe_slug(session_id, "session")
    return _knowledge_dir() / f"_pending-{safe_agent}-{safe_session}.md"


def _log(msg: str) -> None:
    """Escreve linha em ``storage/agent_hooks.log`` (mesmo log do plugin TS)."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")


def _spawn_detached(args: list[str], cwd: Path) -> subprocess.Popen[bytes]:
    """Spawn detached (Windows: ``DETACHED_PROCESS`` + ``CREATE_NEW_PROCESS_GROUP``)."""
    kwargs: dict[str, object] = {
        "cwd": str(cwd),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(args, **kwargs)  # type: ignore[arg-type]


def spawn_summarize_then_embed(
    transcript_path: Path,
    agent_slug: str,
    session_id: str,
) -> int:
    """Orquestra summarize+embed a partir de ``transcript_path``.

    Fluxo:

    1. Idempotencia: se marker existe, no-op (return 0).
    2. Transcript ausente: log + skip (return 0).
    3. summarize.ts --stdout -> stdout em bytes.
    4. Se rc != 0 ou stdout vazio: skip (return 0).
    5. Grava stdout em ``.opencode/rag/knowledge/_pending-<agent>-<session>.md``.
    6. Cria marker (idempotencia).
    7. Spawn embed.ts --file <md> em Popen detached (fire-and-forget).

    Args:
        transcript_path: path do transcript JSONL da sessao.
        agent_slug: slug do agent ativo.
        session_id: id da sessao do opencode.

    Returns:
        Sempre 0 (fire-and-forget; erros sao logados mas nao propagam).
    """
    if not should_record(agent_slug, session_id):
        _log(
            f"[learning] idempotente: marker ja existe "
            f"agent={agent_slug} session={session_id}"
        )
        return 0

    if not transcript_path.exists():
        _log(
            f"[learning] skip: transcript ausente "
            f"agent={agent_slug} session={session_id} path={transcript_path}"
        )
        sys.stderr.write(
            f"[learning] skip: transcript ausente {transcript_path}\n"
        )
        return 0

    _knowledge_dir().mkdir(parents=True, exist_ok=True)
    summarize_args: list[str] = [
        TSX_BIN,
        "tsx",
        ".opencode/rag/summarize.ts",
        "--input",
        str(transcript_path),
        "--agent",
        agent_slug,
        "--stdout",
    ]

    try:
        proc = subprocess.run(
            summarize_args,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=False,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _log(
            f"[learning] summarize timeout agent={agent_slug} session={session_id}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 -- fire-and-forget; log only
        _log(
            f"[learning] summarize erro agent={agent_slug} session={session_id} "
            f"err={exc!r}"
        )
        return 0

    stdout_text = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    stderr_text = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""

    if proc.returncode != 0 or not stdout_text.strip():
        _log(
            f"[learning] summarize vazio/erro agent={agent_slug} session={session_id} "
            f"rc={proc.returncode} stderr={stderr_text.strip()[:200]}"
        )
        return 0

    md_path = _md_path(agent_slug, session_id)
    md_path.write_text(stdout_text, encoding="utf-8")

    embed_args: list[str] = [
        TSX_BIN,
        "tsx",
        ".opencode/rag/embed.ts",
        "--file",
        str(md_path),
        "--agent",
        agent_slug,
    ]
    try:
        _spawn_detached(embed_args, PROJECT_ROOT)
    except Exception as exc:  # noqa: BLE001 -- fire-and-forget; log only
        _log(
            f"[learning] spawn embed erro agent={agent_slug} session={session_id} "
            f"err={exc!r}"
        )

    marker = marker_path(agent_slug, session_id)
    marker.touch()
    _log(
        f"[learning] disparou summarize+embed async agent={agent_slug} "
        f"session={session_id} transcript={transcript_path.name} "
        f"md={md_path.name}"
    )
    return 0


__all__ = [
    "PROJECT_ROOT",
    "LOG_PATH",
    "marker_path",
    "payload_has_edits",
    "resolve_transcript",
    "should_record",
    "spawn_summarize_then_embed",
]
