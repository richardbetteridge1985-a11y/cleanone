import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar, Token
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterator, TypeVar


_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_configured = False
_T = TypeVar("_T")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


class ApplicationLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == "__main__" or record.name.startswith("src.")


@contextmanager
def request_context(request_id: str) -> Iterator[None]:
    token: Token[str] = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


def iter_with_request_context(
    iterable: Iterator[_T],
    request_id: str,
) -> Iterator[_T]:
    iterator = iter(iterable)
    while True:
        try:
            with request_context(request_id):
                item = next(iterator)
        except StopIteration:
            return
        # Reset the context before yielding so streaming callers can resume safely.
        yield item


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    level_name = os.environ.get("CLEANONE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(f"Invalid CLEANONE_LOG_LEVEL: {level_name}")

    default_log_path = Path(__file__).resolve().parents[1] / "logs" / "cleanone.log"
    log_path = Path(os.environ.get("CLEANONE_LOG_FILE", str(default_log_path)))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s request_id=%(request_id)s "
        "%(name)s: %(message)s"
    )
    request_filter = RequestIdFilter()
    application_filter = ApplicationLogFilter()
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
    ]

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(request_filter)
        handler.addFilter(application_filter)
        root_logger.addHandler(handler)

    _configured = True
