"""Throttler com jitter: garante intervalo minimo entre chamadas."""
from __future__ import annotations

import random
import time


class Throttler:
    """Garante ``request_interval_ms`` (+ jitter) entre chamadas de ``wait()``.

    Na primeira chamada (sem registro de ``last_call_at``), NAO dorme — apenas
    marca o timestamp atual. Em chamadas subsequentes, dorme o tempo restante
    caso o intervalo decorrido seja inferior a ``request_interval_ms + jitter``.

    Atributos:
        request_interval_ms: intervalo minimo desejado entre chamadas (ms).
        jitter_ms: largura maxima do jitter aleatorio adicionado ao alvo (ms).
        last_call_at: timestamp ``time.monotonic()`` da ultima chamada; ``None``
            antes da primeira invocacao de ``wait()``.
    """

    def __init__(self, request_interval_ms: int = 2000, jitter_ms: int = 500) -> None:
        self.request_interval_ms: int = request_interval_ms
        self.jitter_ms: int = jitter_ms
        self.last_call_at: float | None = None

    def wait(self) -> None:
        """Bloqueia ate que o intervalo minimo (+jitter) tenha decorrido."""
        if self.last_call_at is None:
            self.last_call_at = time.monotonic()
            return

        now = time.monotonic()
        elapsed_ms: float = (now - self.last_call_at) * 1000.0
        target_ms: float = self.request_interval_ms + random.uniform(0, self.jitter_ms)

        if elapsed_ms < target_ms:
            time.sleep((target_ms - elapsed_ms) / 1000.0)

        self.last_call_at = time.monotonic()
