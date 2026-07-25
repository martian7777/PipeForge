"""Dependencies injected into every agent tool via ``RunContext``.

Holds the DB session, the run/dataset under analysis, the authenticated user, and a
cached DataFrame loader so tools reach the same data without globals — which keeps them
unit-testable with a plain constructed ``AgentDeps``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import pandas as pd

from ..pipeline import ingest

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session
    from ..models import Dataset, Run, User


@dataclass
class AgentDeps:
    """Everything an agent tool needs to read the pipeline's data and state."""

    db: "Session"
    user: "User"
    dataset: "Dataset"
    run: "Optional[Run]" = None
    # Records agent steps to the transcript; wired up by the session runner.
    on_step: Optional[callable] = None
    _df: Optional[pd.DataFrame] = field(default=None, repr=False)

    def dataframe(self) -> pd.DataFrame:
        """Load (and cache) the dataset's DataFrame."""
        if self._df is None:
            self._df = ingest.load_dataframe(self.dataset.path, self.dataset.file_format)
        return self._df
