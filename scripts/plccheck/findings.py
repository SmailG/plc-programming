"""Finding record shared by every checker."""

from __future__ import annotations

from dataclasses import dataclass

# A message or context quotes names from the file, and a context is repeated on every finding
# under it, so one long name times many findings is quadratic in the file size. The longest
# message the tests produce from ordinary names is 203 characters (ST030, with a 17-character
# instance name) and the longest context 26; messages that quote a 300-character file name reach 352.
MAX_FINDING_TEXT = 400
ELLIPSIS = "…"


def _clip(text: str) -> str:
    """`text` as is, or cut to MAX_FINDING_TEXT characters, the last being an ellipsis."""
    if len(text) <= MAX_FINDING_TEXT:
        return text
    return text[: MAX_FINDING_TEXT - len(ELLIPSIS)] + ELLIPSIS


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "warning"
    code: str  # stable rule id, e.g. "ST002"
    message: str
    line: int | None = None
    context: str | None = None  # e.g. "POU FB_Motor body (ST)"

    def __post_init__(self) -> None:
        # Every finding is built through here (error(), warning() and with_context() end in Finding(...)).
        object.__setattr__(self, "message", _clip(self.message))
        if self.context is not None:
            object.__setattr__(self, "context", _clip(self.context))

    def format(self, path: str) -> str:
        where = f"{path}:{self.line}" if self.line else path
        ctx = f" [{self.context}]" if self.context else ""
        return f"{where}: {self.severity} {self.code}: {self.message}{ctx}"

    def as_dict(self, path: str) -> dict:
        return {
            "path": path,
            "line": self.line,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "context": self.context,
        }


def error(code: str, message: str, line: int | None = None, context: str | None = None) -> Finding:
    return Finding("error", code, message, line, context)


def warning(code: str, message: str, line: int | None = None, context: str | None = None) -> Finding:
    return Finding("warning", code, message, line, context)


def with_context(findings: list[Finding], context: str, line_offset: int = 0) -> list[Finding]:
    """Re-anchor findings from an embedded text (ST inside XML) to the outer file."""
    out = []
    for f in findings:
        line = f.line + line_offset if (f.line is not None and line_offset) else f.line
        ctx = context if not f.context else f"{context}; {f.context}"
        out.append(Finding(f.severity, f.code, f.message, line, ctx))
    return out
