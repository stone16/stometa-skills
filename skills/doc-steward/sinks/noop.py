#!/usr/bin/env python3
"""noop sink — the OSS default LEARN adapter (design: references/learning-sink.md §4).

Learning is OFF until a sink is configured. This adapter implements the sink
protocol but writes NOTHING anywhere: no file, no stdout, no side effect. It is the
safe default so that an out-of-the-box LEARN run never dumps a project's
distilled lessons into an unconfigured channel.

Sink protocol (the single seam learn_capture.capture() relies on):

    class Sink:
        def write(self, record: dict) -> None: ...

`record` is the distilled lesson dict produced by learn_capture.capture():
  {"tag": "DOC-*", "lesson": str, "candidate": {6-field matrix}, "severity": str,
   "rule_id": str}.

Stdlib-only. No I/O.
"""


class Sink:
    """No-op sink: accepts a distilled record and discards it (learning OFF)."""

    def write(self, record):  # noqa: D401 — protocol method
        """Discard the record. Intentionally does nothing (no file, no output)."""
        return None
