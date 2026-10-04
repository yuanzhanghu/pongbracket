import logging

from bracket.logger import get_logger


def test_get_logger_returns_named_logger() -> None:
    logger = get_logger("bracket.test_logger")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "bracket.test_logger"


def test_get_logger_has_one_debug_stream_handler_with_formatter() -> None:
    logger = get_logger("bracket.test_logger")

    handlers = logger.handlers
    assert len(handlers) == 1

    handler = handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.level == logging.DEBUG

    formatter = handler.formatter
    assert isinstance(formatter, logging.Formatter)
