"""Configuration errors that prevent a test run from starting."""


class SuiteValidationError(ValueError):
    """The suite does not satisfy Thadam's case format or check contracts."""


class AgentConfigurationError(ValueError):
    """The selected agent cannot be called synchronously with one input."""


class ReportWriteError(OSError):
    """A run report could not be written to its destination."""
