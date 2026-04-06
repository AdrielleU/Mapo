"""Abstract base class for all output writers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OutputWriter(ABC):
    """Base class that every output target must implement."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    def write(self, data: list[dict], metadata: dict) -> None:
        """Write *data* (a list of row dicts) to the target.

        *metadata* carries run-level information such as timestamps, query
        parameters, or row counts that the writer may optionally persist.
        """
        ...
