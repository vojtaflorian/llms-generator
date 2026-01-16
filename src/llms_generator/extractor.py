"""AI-powered content extraction using Google Gen AI SDK."""

import os
import random
import time
from pathlib import Path

from dotenv import load_dotenv
from google.genai import errors as genai_errors
from google.genai import types
from rich.console import Console

from .usage import get_tracker

# Load environment variables from .env file
load_dotenv()

# Retry configuration for rate limiting (loaded after dotenv)
MAX_RETRIES = int(os.environ.get("API_MAX_RETRIES", "5"))
INITIAL_DELAY = float(os.environ.get("API_INITIAL_DELAY", "2.0"))
MAX_DELAY = 60.0

console = Console()

# Singleton client instance
_genai_client = None
_client_config = None


def _get_config() -> dict:
    """Get and validate configuration from environment."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    max_content_length = int(os.environ.get("MAX_CONTENT_LENGTH", "100000"))

    if not project:
        console.print("[red]Error: GOOGLE_CLOUD_PROJECT environment variable is required[/red]")
        console.print("[yellow]Make sure you have:[/yellow]")
        console.print("  1. GOOGLE_CLOUD_PROJECT environment variable set")
        console.print("  2. Application Default Credentials configured")
        console.print("     Run: gcloud auth application-default login")
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is required")

    return {
        "project": project,
        "location": location,
        "model": model,
        "max_content_length": max_content_length,
    }


def get_genai_client():
    """Get or create singleton Google Gen AI client.

    Returns:
        Tuple of (client, config dict)
    """
    global _genai_client, _client_config

    if _genai_client is None:
        from google import genai

        _client_config = _get_config()
        _genai_client = genai.Client(
            vertexai=True,
            project=_client_config["project"],
            location=_client_config["location"],
        )

    return _genai_client, _client_config


def close_genai_client():
    """Explicitly close the GenAI client and release resources."""
    global _genai_client, _client_config

    if _genai_client is not None:
        try:
            _genai_client._api_client.close()
        except Exception:
            pass
        _genai_client = None
        _client_config = None


def load_prompt(prompt_file: str, prompts_dir: Path) -> str:
    """Load prompt template from file."""
    prompt_path = prompts_dir / prompt_file
    if not prompt_path.exists():
        prompt_path = prompts_dir / "default.txt"

    with open(prompt_path) as f:
        return f.read()


def extract_with_ai(
    content: str,
    prompt_template: str,
    dry_run: bool = False,
    source_id: str = "unknown",
) -> str:
    """Extract structured content using Vertex AI.

    Args:
        content: Raw text content to process
        prompt_template: Prompt template with {content} placeholder
        dry_run: If True, skip AI call and return placeholder
        source_id: Source identifier for usage tracking

    Returns:
        Extracted/structured Markdown content
    """
    if dry_run:
        return f"# [DRY RUN]\n\nWould process {len(content)} characters of content."

    # Build the full prompt
    prompt = prompt_template.replace("{content}", content)
    truncated = False

    client, config = get_genai_client()
    max_content_length = config["max_content_length"]

    # Truncate if too long (Gemini has limits)
    if len(prompt) > max_content_length:
        console.print(
            f"  [yellow]Content truncated from {len(prompt)} to {max_content_length} chars[/yellow]"
        )
        # Truncate the content part, keeping the prompt template
        available = max_content_length - len(prompt_template)
        truncated_content = content[:available] + "\n\n[... content truncated ...]"
        prompt = prompt_template.replace("{content}", truncated_content)
        truncated = True

    # Retry loop with exponential backoff
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=config["model"],
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                ),
            )

            # Track character usage (Vertex AI bills per character, not token)
            tracker = get_tracker(config["model"])
            response_text = response.text or ""

            # Use actual character counts for billing estimate
            prompt_chars = len(prompt)
            completion_chars = len(response_text)

            tracker.add(source_id, prompt_chars, completion_chars, truncated)

            return response_text

        except genai_errors.APIError as e:
            # Check for rate limit error (429 RESOURCE_EXHAUSTED)
            if e.code == 429:
                if attempt < MAX_RETRIES - 1:
                    delay = min(INITIAL_DELAY * (2**attempt) + random.uniform(0, 1), MAX_DELAY)
                    console.print(
                        f"  [yellow]Rate limited, waiting {delay:.1f}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES})[/yellow]"
                    )
                    time.sleep(delay)
                    continue

            # Non-retryable error or max retries reached
            console.print(f"  [red]AI extraction failed: {e.message}[/red]")
            return f"# Error\n\nFailed to extract content: {e.message}"

        except Exception as e:
            # Catch any unexpected errors
            console.print(f"  [red]AI extraction failed: {e}[/red]")
            return f"# Error\n\nFailed to extract content: {e}"

    # Should not reach here, but just in case
    return "# Error\n\nMax retries exceeded"


def merge_extractions(extractions: list[str], source_id: str = "content") -> str:
    """Merge multiple extraction results into one document.

    Uses machine-parseable section separators for easy programmatic processing.

    Args:
        extractions: List of Markdown strings from AI extraction
        source_id: Source identifier for separator tags

    Returns:
        Merged Markdown document with section separators
    """
    if len(extractions) == 1:
        return extractions[0]

    # Concatenation with machine-parseable separators
    merged = []
    for i, extraction in enumerate(extractions):
        separator = f"<|llms-section-{source_id}-{i}|>"
        merged.append(f"{separator}\n{extraction}")

    return "\n\n".join(merged)
