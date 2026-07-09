"""领域异常：service 层只抛这些，api 层统一转 HTTP 错误响应 {code, message, detail}。"""


class DomainError(Exception):
    """领域异常基类。"""

    code: str = "domain_error"
    http_status: int = 400

    def __init__(self, message: str, detail: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class InvalidCredentialsError(DomainError):
    code = "invalid_credentials"
    http_status = 401


class NotAuthenticatedError(DomainError):
    code = "not_authenticated"
    http_status = 401


class PermissionDeniedError(DomainError):
    code = "permission_denied"
    http_status = 403


class NotFoundError(DomainError):
    code = "not_found"
    http_status = 404


class ConflictError(DomainError):
    code = "conflict"
    http_status = 409
