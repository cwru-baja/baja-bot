import contextvars
import logging
import uuid

from logtail import LogtailHandler


# For logging purposes. Stores a trace_id to be used for all logs.
trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id",
    default=None,
)


def new_trace():
    """Call whenever the trace_id must be set again. At the start of every traceable async method."""
    trace_id.set(str(uuid.uuid4()))


class TraceFilter(logging.Filter):
    def filter(self, record):
        record.trace_id = trace_id.get()
        return True