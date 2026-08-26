"""Coletor/Scraper: descobre e baixa documentos dos portais oficiais.

Importante: este modulo adiciona ``.opencode/`` ao ``sys.path`` no momento da
importacao do pacote, para que ``downloader.py`` e ``portal_index.py`` consigam
fazer ``from hooks.domain_guard import validate_url, ALLOWED_DOMAINS``.

Isso e essencial para o fail-closed do guardrail: se o path nao for
encontrado, o coletor LEVANTA ``RuntimeError`` (PLAN_SPRINT4 A.1)
em vez de aceitar tudo silenciosamente.

A flag ``DFE_DISABLE_HOOKS_BOOTSTRAP`` desativa esse bootstrap para
testes que precisam simular a ausencia do guardrail (ex.: fail-closed).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if not os.environ.get("DFE_DISABLE_HOOKS_BOOTSTRAP"):
    _HOOKS_PKG_PARENT: Path = Path(__file__).resolve().parents[2] / ".opencode"
    if str(_HOOKS_PKG_PARENT) not in sys.path:
        sys.path.insert(0, str(_HOOKS_PKG_PARENT))

__all__ = ["portal_index", "downloader", "__main__"]
