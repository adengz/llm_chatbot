class InfrastructureException(Exception):
    pass


class LLMStreamingError(InfrastructureException):
    pass


class ToolExecutionError(InfrastructureException):
    pass
