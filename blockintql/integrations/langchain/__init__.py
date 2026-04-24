"""LangChain integration exports.

The LangChain tool dependencies are optional for the core CLI package, so avoid
importing them until a caller explicitly requests the toolkit.
"""

__all__ = ["BlockINTQLTools"]


def __getattr__(name):
    if name == "BlockINTQLTools":
        from .tool import BlockINTQLTools

        return BlockINTQLTools
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
