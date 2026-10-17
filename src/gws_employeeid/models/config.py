"""Configuration models for Employee ID assignment."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AssignmentConfig:
    """Configuration for generating and assigning Employee IDs."""

    start_id: int | None = None
    prefix: str = ""
    pad_width: int = 0
    exclude_suspended: bool = False
    force: bool = False
    dry_run: bool = False

    def format_id(self, numeric_id: int) -> str:
        """Format an integer ID with optional prefix and padding."""
        if self.pad_width > 0:
            formatted_num = f"{numeric_id:0{self.pad_width}d}"
        else:
            formatted_num = str(numeric_id)
        return f"{self.prefix}{formatted_num}"
