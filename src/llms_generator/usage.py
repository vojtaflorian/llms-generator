"""Token and character usage tracking for AI calls."""

from dataclasses import dataclass, field
from rich.console import Console
from rich.table import Table

console = Console()

# Gemini pricing (per 1M characters) - Vertex AI EU region
# https://cloud.google.com/vertex-ai/generative-ai/pricing
# Note: Vertex AI bills per CHARACTER, not per token!
PRICING = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
}

# Default context window limits (characters)
CONTEXT_LIMITS = {
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
    "gemini-1.5-flash": 1_000_000,
    "gemini-1.5-pro": 2_000_000,
}


@dataclass
class SourceUsage:
    """Character usage for a single source."""

    source_id: str
    prompt_chars: int = 0
    completion_chars: int = 0
    total_chars: int = 0
    calls: int = 0
    truncated: bool = False

    def add(self, prompt: int, completion: int, truncated: bool = False) -> None:
        """Add usage from an AI call."""
        self.prompt_chars += prompt
        self.completion_chars += completion
        self.total_chars += prompt + completion
        self.calls += 1
        if truncated:
            self.truncated = True


@dataclass
class UsageTracker:
    """Tracks character usage across all sources."""

    model: str = "gemini-2.0-flash"
    sources: dict[str, SourceUsage] = field(default_factory=dict)

    def add(
        self,
        source_id: str,
        prompt_chars: int,
        completion_chars: int,
        truncated: bool = False,
    ) -> None:
        """Record usage for a source."""
        if source_id not in self.sources:
            self.sources[source_id] = SourceUsage(source_id=source_id)
        self.sources[source_id].add(prompt_chars, completion_chars, truncated)

    @property
    def total_prompt_chars(self) -> int:
        """Total input characters across all sources."""
        return sum(s.prompt_chars for s in self.sources.values())

    @property
    def total_completion_chars(self) -> int:
        """Total output characters across all sources."""
        return sum(s.completion_chars for s in self.sources.values())

    @property
    def total_chars(self) -> int:
        """Total characters across all sources."""
        return sum(s.total_chars for s in self.sources.values())

    @property
    def total_calls(self) -> int:
        """Total AI calls across all sources."""
        return sum(s.calls for s in self.sources.values())

    def estimate_cost(self) -> float:
        """Estimate total cost in USD based on characters."""
        pricing = PRICING.get(self.model, PRICING["gemini-2.0-flash"])
        input_cost = (self.total_prompt_chars / 1_000_000) * pricing["input"]
        output_cost = (self.total_completion_chars / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def print_summary(self) -> None:
        """Print usage summary table."""
        if not self.sources:
            return

        console.print()
        console.print("[bold]Usage Summary (billable characters)[/bold]")
        console.print()

        # Per-source table
        table = Table(show_header=True, header_style="bold")
        table.add_column("Source")
        table.add_column("Calls", justify="right")
        table.add_column("Input", justify="right")
        table.add_column("Output", justify="right")
        table.add_column("Total", justify="right")
        table.add_column("Status")

        for source in sorted(self.sources.values(), key=lambda s: s.total_chars, reverse=True):
            status = "[yellow]TRUNCATED[/yellow]" if source.truncated else "[green]OK[/green]"
            table.add_row(
                source.source_id,
                str(source.calls),
                f"{source.prompt_chars:,}",
                f"{source.completion_chars:,}",
                f"{source.total_chars:,}",
                status,
            )

        console.print(table)

        # Totals
        console.print()
        pricing = PRICING.get(self.model, PRICING["gemini-2.0-flash"])
        cost = self.estimate_cost()

        console.print(f"[bold]Total:[/bold] {self.total_chars:,} chars ({self.total_calls} API calls)")
        console.print(f"  Input:  {self.total_prompt_chars:,} chars (${pricing['input']}/1M)")
        console.print(f"  Output: {self.total_completion_chars:,} chars (${pricing['output']}/1M)")
        console.print(f"  [bold]Estimated cost: ${cost:.4f}[/bold]")

        # Warnings
        truncated_sources = [s for s in self.sources.values() if s.truncated]
        if truncated_sources:
            console.print()
            console.print("[yellow]Warning: Some sources were truncated due to size limits:[/yellow]")
            for source in truncated_sources:
                console.print(f"  - {source.source_id}: Consider splitting into smaller chunks")


# Global tracker instance
_tracker: UsageTracker | None = None


def get_tracker(model: str = "gemini-2.0-flash") -> UsageTracker:
    """Get or create the global usage tracker."""
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker(model=model)
    return _tracker


def reset_tracker() -> None:
    """Reset the global usage tracker."""
    global _tracker
    _tracker = None
