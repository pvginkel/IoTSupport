"""Domain-specific exceptions with user-ready messages for the IoT support system."""


class BusinessLogicException(Exception):
    """Base exception class for business logic errors.

    All business logic exceptions include user-ready messages that can be
    displayed directly in the UI without client-side message construction.
    """

    def __init__(self, message: str, error_code: str) -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class RecordNotFoundException(BusinessLogicException):
    """Exception raised when a requested record is not found."""

    def __init__(self, resource_type: str, identifier: str) -> None:
        message = f"{resource_type} {identifier} was not found"
        super().__init__(message, error_code="RECORD_NOT_FOUND")


class RecordExistsException(BusinessLogicException):
    """Exception raised when attempting to create a record that already exists."""

    def __init__(self, resource_type: str, identifier: str) -> None:
        message = f"{resource_type} for {identifier} already exists"
        super().__init__(message, error_code="RECORD_EXISTS")


class InvalidOperationException(BusinessLogicException):
    """Exception raised when an operation cannot be performed due to business rules."""

    def __init__(self, operation: str, cause: str) -> None:
        self.operation = operation
        self.cause = cause
        message = f"Cannot {operation} because {cause}"
        super().__init__(message, error_code="INVALID_OPERATION")


class ValidationException(BusinessLogicException):
    """Exception raised when validation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="VALIDATION_FAILED")


class ExternalServiceException(BusinessLogicException):
    """Exception raised when an external service call fails."""

    def __init__(self, operation: str, cause: str) -> None:
        self.operation = operation
        self.cause = cause
        message = f"Cannot {operation} because external service failed: {cause}"
        super().__init__(message, error_code="EXTERNAL_SERVICE_ERROR")


class ProcessingException(BusinessLogicException):
    """Exception raised when internal processing fails."""

    def __init__(self, operation: str, cause: str) -> None:
        self.operation = operation
        self.cause = cause
        message = f"Cannot {operation} because processing failed: {cause}"
        super().__init__(message, error_code="PROCESSING_ERROR")


class AuthenticationException(BusinessLogicException):
    """Exception raised when authentication fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="AUTHENTICATION_REQUIRED")


class AuthorizationException(BusinessLogicException):
    """Exception raised when authorization fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="AUTHORIZATION_FAILED")


class RouteNotAvailableException(BusinessLogicException):
    """Exception raised when a route is not available in the current environment."""

    def __init__(self, message: str = "This route is not available") -> None:
        super().__init__(message, error_code="ROUTE_NOT_AVAILABLE")
