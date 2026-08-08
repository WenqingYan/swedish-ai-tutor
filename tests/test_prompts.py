"""Tests for prompt loading and rendering."""

import pytest

from swedish_ai_tutor.prompts import load_prompt, render_prompt


class TestLoadPrompt:
    """Test prompt template loading."""

    def test_load_sentence_analysis(self) -> None:
        """Can load the v1 sentence analysis prompt."""
        prompt = load_prompt("v1", "sentence_analysis")
        assert "{{sentence}}" in prompt
        assert "Swedish" in prompt
        assert "JSON" in prompt

    def test_load_word_enrichment(self) -> None:
        """Manual word prompt requests morphology and a bilingual example."""
        prompt = load_prompt("v1", "word_enrichment")
        assert "{{word}}" in prompt
        assert '"example"' in prompt
        assert "supine" in prompt

    def test_load_nonexistent_raises(self) -> None:
        """Loading a nonexistent prompt raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            load_prompt("v99", "nonexistent")

    def test_prompt_contains_required_output_fields(self) -> None:
        """Prompt instructs LLM to produce all required fields."""
        prompt = load_prompt("v1", "sentence_analysis")
        required_fields = [
            "original",
            "translation",
            "grammar",
            "phrases",
            "vocabulary",
            "examples",
            "sfi_notes",
        ]
        for field in required_fields:
            assert f'"{field}"' in prompt, f"Missing field in prompt: {field}"

    def test_prompt_mentions_morphology(self) -> None:
        """Prompt includes morphology requirements for verbs, nouns, adjectives."""
        prompt = load_prompt("v1", "sentence_analysis")
        assert "verb" in prompt.lower()
        assert "noun" in prompt.lower()
        assert "adjective" in prompt.lower()
        assert "imperative" in prompt.lower()
        assert "supine" in prompt.lower()


class TestRenderPrompt:
    """Test prompt template rendering."""

    def test_render_replaces_placeholder(self) -> None:
        """Replaces {{variable}} with provided value."""
        template = "Analyze: {{sentence}}"
        result = render_prompt(template, sentence="Hej på dig.")
        assert result == "Analyze: Hej på dig."

    def test_render_multiple_placeholders(self) -> None:
        """Replaces multiple different placeholders."""
        template = "{{greeting}}, {{name}}!"
        result = render_prompt(template, greeting="Hej", name="Sara")
        assert result == "Hej, Sara!"

    def test_render_with_actual_prompt(self) -> None:
        """Renders the actual sentence analysis prompt with a sample sentence."""
        template = load_prompt("v1", "sentence_analysis")
        rendered = render_prompt(template, sentence="Det är varmt idag.")
        assert "Det är varmt idag." in rendered
        assert "{{sentence}}" not in rendered

    def test_render_preserves_unmatched_placeholders(self) -> None:
        """Unmatched placeholders remain in the output."""
        template = "{{known}} and {{unknown}}"
        result = render_prompt(template, known="Hello")
        assert result == "Hello and {{unknown}}"
