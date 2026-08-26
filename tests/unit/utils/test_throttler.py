"""Testes para src.utils.throttler."""
from __future__ import annotations

import time

import pytest

from src.utils.throttler import Throttler


def test_throttler_first_call_does_not_sleep(mocker) -> None:
    mock_sleep = mocker.patch("time.sleep")
    mocker.patch("time.monotonic", return_value=1000.0)

    throttler = Throttler(request_interval_ms=500, jitter_ms=100)
    throttler.wait()

    mock_sleep.assert_not_called()
    assert throttler.last_call_at == 1000.0


def test_throttler_second_call_respects_interval(mocker) -> None:
    time_values = [1000.0, 1000.05, 1000.20]
    mocker.patch("time.monotonic", side_effect=time_values)
    mock_sleep = mocker.patch("time.sleep")

    throttler = Throttler(request_interval_ms=200, jitter_ms=0)
    throttler.wait()
    throttler.wait()

    mock_sleep.assert_called_once()
    sleep_seconds = mock_sleep.call_args.args[0]
    assert sleep_seconds == pytest.approx(0.150, abs=1e-6)


def test_throttler_three_calls_takes_at_least_two_intervals() -> None:
    throttler = Throttler(request_interval_ms=200, jitter_ms=0)

    t_start = time.monotonic()
    throttler.wait()
    throttler.wait()
    throttler.wait()
    t_end = time.monotonic()

    elapsed_ms = (t_end - t_start) * 1000.0
    # Windows tem granularidade de timer ~15.625ms — sleeps de 200ms podem retornar
    # ~10ms mais cedo. Tolerancia de 20ms valida "dois intervalos completos respeitados".
    assert elapsed_ms == pytest.approx(400.0, abs=20.0)


def test_throttler_does_not_sleep_when_interval_already_exceeded(mocker) -> None:
    timeline = [
        1000.0,   # wait #1: sets last_call_at (None branch)
        1100.0,   # wait #2: now (elapsed=100s >> target=50ms)
        1100.0,   # wait #2: updates last_call_at (after no-sleep branch)
    ]
    mocker.patch("time.monotonic", side_effect=timeline)
    mock_sleep = mocker.patch("time.sleep")

    throttler = Throttler(request_interval_ms=50, jitter_ms=0)
    throttler.wait()
    throttler.wait()

    mock_sleep.assert_not_called()


def test_throttler_jitter_zero_is_deterministic(mocker) -> None:
    timeline = [
        1000.00,  # wait #1: sets last_call_at (None branch)
        1000.01,  # wait #2: now, elapsed=10ms
        1000.06,  # wait #2: updates last_call_at after sleeping 40ms
        1000.07,  # wait #3: now, elapsed=(1000.07-1000.06)*1000=10ms
        1000.12,  # wait #3: updates last_call_at after sleeping 40ms
    ]
    mocker.patch("time.monotonic", side_effect=timeline)
    mock_sleep = mocker.patch("time.sleep")

    throttler = Throttler(request_interval_ms=50, jitter_ms=0)
    throttler.wait()
    throttler.wait()
    throttler.wait()

    assert mock_sleep.call_count == 2
    first_sleep = mock_sleep.call_args_list[0].args[0]
    second_sleep = mock_sleep.call_args_list[1].args[0]
    assert first_sleep == pytest.approx(0.040, abs=1e-6)
    assert second_sleep == pytest.approx(0.040, abs=1e-6)
