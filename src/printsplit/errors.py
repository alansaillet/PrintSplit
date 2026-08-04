"""Exception hierarchy.

Every error PrintSplit raises on purpose derives from :class:`PrintSplitError`,
so a caller -- a GUI, say -- can catch that one class and show the message,
rather than guessing which of ValueError / KeyError / OSError might surface.
"""

from __future__ import annotations


class PrintSplitError(Exception):
    """Base class for every error PrintSplit raises deliberately."""


class ConfigError(PrintSplitError):
    """A config file is missing, malformed, or has an invalid value."""


class SourceError(PrintSplitError):
    """The source PDF is missing, unreadable, or has no tileable content."""


class LayoutError(PrintSplitError):
    """The requested combination of scale, paper and overlap cannot be tiled."""


__all__ = ["PrintSplitError", "ConfigError", "SourceError", "LayoutError"]
