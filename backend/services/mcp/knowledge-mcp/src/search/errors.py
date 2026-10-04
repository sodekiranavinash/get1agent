from __future__ import annotations


class RetrievalError(Exception):
    """A caller-facing retrieval failure that maps to a structured JSON error."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
