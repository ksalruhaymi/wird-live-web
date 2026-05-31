class CallProviderError(Exception):
    """Raised when call provider configuration or token generation fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CallValidationError(Exception):
    """Raised when call request validation fails (teacher, session type, etc.)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
