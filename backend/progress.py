"""
Job progress tracking for the Mapo pipeline.
"""
from dataclasses import dataclass, field
from time import time


@dataclass
class JobProgress:
    total_queries: int = 0
    completed_queries: int = 0
    total_places_found: int = 0
    places_scraped: int = 0
    start_time: float = field(default_factory=time)

    @property
    def elapsed(self) -> float:
        """Seconds since the job started."""
        return time() - self.start_time

    @property
    def avg_per_place(self) -> float:
        """Rolling average seconds per place scraped."""
        if self.places_scraped == 0:
            return 0.0
        return self.elapsed / self.places_scraped

    @property
    def eta_seconds(self) -> float:
        """Estimated seconds remaining based on rolling average."""
        remaining = self.total_places_found - self.places_scraped
        if remaining <= 0 or self.avg_per_place == 0.0:
            return 0.0
        return remaining * self.avg_per_place

    @property
    def percent(self) -> float:
        """Completion percentage (0-100)."""
        if self.total_places_found == 0:
            if self.total_queries == 0:
                return 0.0
            return (self.completed_queries / self.total_queries) * 100.0
        return (self.places_scraped / self.total_places_found) * 100.0

    def to_dict(self) -> dict:
        """Serialize progress to a plain dict for JSON transport."""
        return {
            "total_queries": self.total_queries,
            "completed_queries": self.completed_queries,
            "total_places_found": self.total_places_found,
            "places_scraped": self.places_scraped,
            "elapsed": round(self.elapsed, 2),
            "avg_per_place": round(self.avg_per_place, 3),
            "eta_seconds": round(self.eta_seconds, 1),
            "percent": round(self.percent, 1),
        }
