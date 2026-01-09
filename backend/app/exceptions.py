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
