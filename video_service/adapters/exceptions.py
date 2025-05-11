"""Module for service exceptions."""


class VideoStreamNotFoundError(Exception):
    """Class representing custom exception."""

    def __init__(self, message: str) -> None:
        """Initialize the error."""
        # Call the base class constructor with the parameters it needs
        super().__init__(message)
