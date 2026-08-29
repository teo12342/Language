class NexusError(Exception):
    """Base class for all Nexus language errors."""

    def __init__(self, message: str, line: int | None = None):
        self.message = message
        self.line = line
        location = f" [line {line}]" if line is not None else ""
        super().__init__(f"{message}{location}")


class NexusSyntaxError(NexusError):
    pass


class NexusRuntimeError(NexusError):
    pass
