import contextvars
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


class TraceLogtailHandler(LogtailHandler):
    def emit(self, record):
        # inject trace_id into the structured payload
        if not hasattr(record, "extra"):
            record.extra = {}

        record.extra["trace_id"] = trace_id.get()
        record.trace_id = trace_id.get()

        return super().emit(record)