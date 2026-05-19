import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

from loguru import logger


class InfrastructureException(Exception):
    pass


class ModelListError(InfrastructureException):
    pass


class LLMStreamingError(InfrastructureException):
    pass


class ToolExecutionError(InfrastructureException):
    pass


class DatabaseError(InfrastructureException):
    pass


P = ParamSpec("P")
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])
AsyncFn = Callable[P, Awaitable[T]]
AsyncGenFn = Callable[P, AsyncGenerator[T, None]]


def reraise_as(
    exception_cls: type[InfrastructureException],
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        if inspect.isasyncgenfunction(func):
            asyncgen_func = cast(AsyncGenFn[..., Any], func)

            @wraps(func)
            async def asyncgen_wrapper(
                *args: Any, **kwargs: Any
            ) -> AsyncGenerator[Any, None]:
                try:
                    async for item in asyncgen_func(*args, **kwargs):
                        yield item
                except Exception as exc:
                    logger.exception("Unhandled exception in {}", func.__qualname__)
                    if isinstance(exc, exception_cls):
                        raise
                    raise exception_cls(str(exc)) from exc

            return cast(F, asyncgen_wrapper)

        async_func = cast(AsyncFn[..., Any], func)

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await async_func(*args, **kwargs)
            except Exception as exc:
                logger.exception("Unhandled exception in {}", func.__qualname__)
                if isinstance(exc, exception_cls):
                    raise
                raise exception_cls(str(exc)) from exc

        return cast(F, async_wrapper)

    return decorator
