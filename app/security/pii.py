"""PII redaction before anything is sent to the LLM, and restoration of tokens in model output."""
import re

PATTERNS = [
    ("KARTA", re.compile(r"\b\d{4}[ \-]?(?:\d{4}|\*{4})[ \-]?(?:\d{4}|\*{4})[ \-]?\d{4}\b")),
    ("HISOB", re.compile(r"\b\d{20}\b")),
    ("TEL", re.compile(r"\+?998[\s\-]?\(?\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
]
TOKEN_RE = re.compile(r"\[(?:KARTA|HISOB|TEL|EMAIL|ISM)_\d+\]")


class Redactor:
    """Keeps a stable mapping original <-> token for one conversation."""

    def __init__(self, names: list[str] | None = None):
        self.names = sorted(names or [], key=len, reverse=True)
        self.to_token: dict[str, str] = {}
        self.to_original: dict[str, str] = {}
        self.counts: dict[str, int] = {}

    def _token(self, kind: str, original: str) -> str:
        if original in self.to_token:
            return self.to_token[original]
        self.counts[kind] = self.counts.get(kind, 0) + 1
        token = f"[{kind}_{self.counts[kind]}]"
        self.to_token[original] = token
        self.to_original[token] = original
        return token

    def redact(self, text: str) -> str:
        for kind, rx in PATTERNS:
            text = rx.sub(lambda m: self._token(kind, m.group(0)), text)
        for name in self.names:
            text = re.sub(rf"\b{re.escape(name)}\b", lambda m: self._token("ISM", name), text)
        return text

    def restore(self, text: str) -> str:
        return TOKEN_RE.sub(lambda m: self.to_original.get(m.group(0), m.group(0)), text)


class StreamRestorer:
    """Restores tokens in streamed text; holds back a trailing partial '[TOKEN' until it completes."""

    def __init__(self, redactor: Redactor):
        self.r = redactor
        self.buf = ""

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        cut = self.buf.rfind("[")
        if cut != -1 and "]" not in self.buf[cut:] and len(self.buf) - cut < 16:
            ready, self.buf = self.buf[:cut], self.buf[cut:]
        else:
            ready, self.buf = self.buf, ""
        return self.r.restore(ready)

    def flush(self) -> str:
        out, self.buf = self.r.restore(self.buf), ""
        return out


def mask_card(card: str) -> str:
    digits = re.sub(r"\D", "", card)
    return f"{digits[:4]} **** **** {digits[-4:]}" if len(digits) >= 12 else card


def mask_account(acc: str) -> str:
    return f"{acc[:5]}••••••••••{acc[-4:]}" if len(acc) >= 12 else acc
