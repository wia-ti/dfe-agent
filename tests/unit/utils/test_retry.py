"""Testes para src.utils.retry."""
from __future__ import annotations

import pytest

from src.utils.retry import retry


def test_retry_returns_value_on_first_success() -> None:
    result = retry(lambda: 42, attempts=3, backoff_seconds=0.001)
    assert result == 42


def test_retry_returns_value_after_failures() -> None:
    state = {"n": 0}

    def flaky() -> str:
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError(f"fail {state['n']}")
        return "ok"

    result = retry(flaky, attempts=5, backoff_seconds=0.001)
    assert result == "ok"
    assert state["n"] == 3


def test_retry_exhausts_attempts_and_raises_last_exception(mocker) -> None:
    func = mocker.Mock(side_effect=ValueError("boom"))

    with pytest.raises(ValueError, match="boom"):
        retry(func, attempts=2, backoff_seconds=0.001)

    assert func.call_count == 2


def test_retry_does_not_retry_unlisted_exception() -> None:
    state = {"n": 0}

    def kaboom() -> None:
        state["n"] += 1
        raise KeyError("not in tuple")

    with pytest.raises(KeyError, match="not in tuple"):
        retry(kaboom, attempts=5, exceptions=(ValueError,), backoff_seconds=0.001)

    assert state["n"] == 1


def test_retry_default_exceptions_catches_exception_subclasses() -> None:
    state = {"n": 0}

    def flaky() -> str:
        state["n"] += 1
        if state["n"] < 2:
            raise RuntimeError("transient")
        return "recovered"

    result = retry(flaky, attempts=3, backoff_seconds=0.001)
    assert result == "recovered"
    assert state["n"] == 2


def test_retry_with_zero_attempts_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError, match="retry:"):
        retry(lambda: "never", attempts=0, backoff_seconds=0.001)
