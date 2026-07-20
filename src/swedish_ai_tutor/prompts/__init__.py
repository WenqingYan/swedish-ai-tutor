"""Prompt template loading and rendering utilities."""

from pathlib import Path

# Resolve the prompts directory relative to this module
_PROMPTS_DIR = Path(__file__).parent


def load_prompt(version: str, name: str) -> str:
    """Load a prompt template from the prompts directory.

    Args:
        version: Prompt version (e.g., "v1").
        name: Prompt filename without extension (e.g., "sentence_analysis").

    Returns:
        The raw prompt template string.

    Raises:
        FileNotFoundError: If the prompt file doesn't exist.
    """
    path = _PROMPTS_DIR / version / f"{name}.txt"
    if not path.exists():
        msg = f"Prompt template not found: {path}"
        raise FileNotFoundError(msg)
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, **variables: str) -> str:
    """Render a prompt template by replacing {{variable}} placeholders.

    Args:
        template: The prompt template string.
        **variables: Key-value pairs for placeholder replacement.

    Returns:
        The rendered prompt with all placeholders filled.
    """
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result
