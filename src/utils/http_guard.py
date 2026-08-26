"""HTTP guard in-process: envolve ``requests.get`` para enforce de ``ALLOWED_DOMAINS``.

Esta camada existe para satisfazer o criterio do PLAN_SPRINT4 A.3:
    ``git grep "from domain_guard" src/`` retorna 0.

Ou seja, NENHUM modulo em ``src/`` pode importar ``hooks.domain_guard``
diretamente; tudo passa por esta camada.

API publica:
    - ``validate_url(url)``: valida uma URL contra ``ALLOWED_DOMAINS``.
      Retorna ``bool`` (igual ao ``hooks.domain_guard.validate_url``).
    - ``safe_get(url, **kwargs)``: chama ``validate_url`` e, se passar,
      delega para ``requests.get``. Levanta ``PermissionError`` se a
      URL estiver bloqueada.
    - ``safe_session_get(session, url, **kwargs)``: variante para
      ``requests.Session().get(...)``.
    - ``install_http_guard()``: monkey-patch ``requests.get`` e
      ``requests.Session.get`` para chamar ``safe_get`` /
      ``safe_session_get`` respectivamente.
    - ``uninstall_http_guard()``: desfaz o monkey-patch.

Origem do guardrail (PLAN_SPRINT4 A.1, A.3):
    - Fail-closed: se ``hooks.domain_guard`` nao puder ser importado,
      este modulo LEVANTA ``RuntimeError`` na importacao. Nenhum
      stub permissivo.
    - A politica de match exato (sem suffix-match) e definida em
      ``.opencode/hooks/domain_guard.py`` (BLOQUEANTE #3).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from src.utils.syspath_bootstrap import ensure_sys_path

ensure_sys_path()

try:
    from hooks.domain_guard import ALLOWED_DOMAINS, validate_url  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "domain_guard indisponivel; guardrail exige-o"
    ) from exc


__all__ = [
    "ALLOWED_DOMAINS",
    "install_http_guard",
    "safe_get",
    "safe_session_get",
    "uninstall_http_guard",
    "validate_url",
]


def _project_root() -> Path:
    """Tenta localizar a raiz do projeto (para logs)."""
    return Path(__file__).resolve().parents[2]


def safe_get(url: str, **kwargs: Any) -> requests.Response:
    """Wrapper sobre ``requests.get`` que valida a URL antes do I/O.

    Args:
        url: URL a ser requisitada.
        **kwargs: Argumentos adicionais passados para ``requests.get``.

    Returns:
        ``requests.Response`` em caso de URL autorizada.

    Raises:
        PermissionError: Se a URL NAO passa em ``validate_url``.
    """
    if not validate_url(url, ALLOWED_DOMAINS):
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        raise PermissionError(
            f"URL bloqueada pelo guardrail: {url} (hostname={hostname!r})"
        )
    return _original_requests_get(url, **kwargs)


def safe_session_get(
    session: requests.Session, url: str, **kwargs: Any
) -> requests.Response:
    """Wrapper sobre ``session.get`` que valida a URL antes do I/O."""
    if not validate_url(url, ALLOWED_DOMAINS):
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        raise PermissionError(
            f"URL bloqueada pelo guardrail: {url} (hostname={hostname!r})"
        )
    return _original_session_get(session, url, **kwargs)


_original_requests_get = requests.get
_original_session_get = requests.Session.get
_guards_installed: bool = False


def install_http_guard() -> None:
    """Instala o guard HTTP in-process.

    Monkey-patches ``requests.get`` (mod-level) e
    ``requests.Session.get`` (instance-level) para invocar
    ``safe_get`` / ``safe_session_get`` antes do I/O.

    Idempotente: chamadas duplicadas sao no-op.
    """
    global _guards_installed
    if _guards_installed:
        return
    requests.get = safe_get  # type: ignore[assignment]
    requests.Session.get = safe_session_get  # type: ignore[assignment,method-assign]
    _guards_installed = True


def uninstall_http_guard() -> None:
    """Desfaz o monkey-patch instalado por ``install_http_guard``.

    Idempotente: no-op se o guard nao estiver instalado.
    """
    global _guards_installed
    if not _guards_installed:
        return
    requests.get = _original_requests_get  # type: ignore[assignment]
    requests.Session.get = _original_session_get  # type: ignore[assignment,method-assign]
    _guards_installed = False
