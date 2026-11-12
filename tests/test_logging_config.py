import logging
from contextvars import copy_context

from src.logging_config import (
    RequestIdFilter,
    iter_with_request_context,
    request_context,
)


def test_request_filter_attaches_current_request_id():
    record = logging.LogRecord("src.ui", logging.INFO, __file__, 1, "test", (), None)

    with request_context("request-123"):
        assert RequestIdFilter().filter(record)

    assert record.request_id == "request-123"


def test_request_filter_uses_placeholder_outside_a_request():
    record = logging.LogRecord("src.main", logging.INFO, __file__, 1, "test", (), None)

    RequestIdFilter().filter(record)

    assert record.request_id == "-"


def test_streaming_iterator_sets_request_id_for_each_step_only():
    def records():
        for _ in range(2):
            record = logging.LogRecord("src.ui", logging.INFO, __file__, 1, "test", (), None)
            RequestIdFilter().filter(record)
            yield record.request_id

    iterator = iter_with_request_context(records(), "stream-123")
    assert copy_context().run(next, iterator) == "stream-123"
    assert copy_context().run(next, iterator) == "stream-123"

    try:
        copy_context().run(next, iterator)
    except StopIteration:
        pass
    else:
        raise AssertionError("The streaming iterator should be exhausted")

    outside_record = logging.LogRecord("src.ui", logging.INFO, __file__, 1, "test", (), None)
    RequestIdFilter().filter(outside_record)
    assert outside_record.request_id == "-"
