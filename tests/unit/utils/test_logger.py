"""Testes para src.utils.logger."""
from __future__ import annotations

import logging

from src.utils.logger import get_logger


def test_get_logger_returns_logger_with_provided_name() -> None:
    logger = get_logger("test_logger_name_attr")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_logger_name_attr"


def test_get_logger_has_at_least_one_stream_handler() -> None:
    logger = get_logger("test_logger_has_handler")
    assert len(logger.handlers) >= 1
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)


def test_get_logger_handler_uses_expected_format() -> None:
    logger = get_logger("test_logger_format")
    formatter = logger.handlers[0].formatter
    assert formatter is not None
    assert formatter._fmt == "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def test_get_logger_does_not_propagate_to_root() -> None:
    logger = get_logger("test_logger_no_propagate")
    assert logger.propagate is False


def test_get_logger_respects_level_argument() -> None:
    logger = get_logger("test_logger_level_debug", level=logging.DEBUG)
    assert logger.level == logging.DEBUG


def test_get_logger_is_idempotent_no_duplicate_handlers() -> None:
    first = get_logger("test_logger_idempotent_unique")
    handlers_after_first = len(first.handlers)
    second = get_logger("test_logger_idempotent_unique")
    assert first is second
    assert len(second.handlers) == handlers_after_first
