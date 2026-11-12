import logging

from src.logging_config import RequestIdFilter, request_context


def test_request_filter_attaches_current_request_id():
    record = logging.LogRecord("src.ui", logging.INFO, __file__, 1, "test", (), None)

    with request_context("request-123"):
        assert RequestIdFilter().filter(record)

    assert record.request_id == "request-123"


def test_request_filter_uses_placeholder_outside_a_request():
    record = logging.LogRecord("src.main", logging.INFO, __file__, 1, "test", (), None)

    RequestIdFilter().filter(record)

    assert record.request_id == "-"
