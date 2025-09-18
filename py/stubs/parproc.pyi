from typing import Any, Callable, TypeVar, overload

F = TypeVar('F', bound=Callable[..., Any])

class Proc:
    """Decorator for processes"""

    @overload
    def __init__(
        self,
        name: str | None = None,
        *,
        deps: list[str] | None = None,
        locks: list[str] | None = None,
        now: bool = False,
        args: dict[str, Any] | None = None,
        proto: Any | None = None,
        timeout: float | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        name: str | None = None,
        f: F | None = None,
        *,
        deps: list[str] | None = None,
        locks: list[str] | None = None,
        now: bool = False,
        args: dict[str, Any] | None = None,
        proto: Any | None = None,
        timeout: float | None = None,
    ) -> None: ...

    def __call__(self, f: F) -> F: ...

class Proto:
    """Decorator for process prototypes"""

    @overload
    def __init__(
        self,
        name: str | None = None,
        *,
        deps: list[str] | None = None,
        locks: list[str] | None = None,
        now: bool = False,
        args: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        name: str | None = None,
        f: F | None = None,
        *,
        deps: list[str] | None = None,
        locks: list[str] | None = None,
        now: bool = False,
        args: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> None: ...

    def __call__(self, f: F) -> F: ...

def wait_clear(exception_on_failure: bool = False) -> None: ...
