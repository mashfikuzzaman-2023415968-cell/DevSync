"""Upload errors: one generic, safe message per problem (never echoing file contents)."""

from __future__ import annotations

from app.core.errors import DomainError, ErrorCode


class UploadRejectedError(DomainError):
    """The file is not acceptable (type, content, size or structure)."""

    code = ErrorCode.VALIDATION_ERROR

    def __init__(self, reason: str) -> None:
        super().__init__(reason, fields={"file": reason})


class UploadTooLargeError(DomainError):
    """The file is bigger than allowed for its kind."""

    code = ErrorCode.PAYLOAD_TOO_LARGE
