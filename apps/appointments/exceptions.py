class AppointmentError(Exception):
    """Domain error with an Arabic message suitable for API responses."""

    def __init__(self, message: str, *, code: str = "appointment_error", status: int = 400):
        self.message = message
        self.code = code
        self.status = status
        super().__init__(message)
