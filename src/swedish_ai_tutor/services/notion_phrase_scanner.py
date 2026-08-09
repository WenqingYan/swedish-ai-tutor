"""Import learner-bolded Notion expressions into the shared phrase catalog."""

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from notion_client import AsyncClient as NotionClient
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from swedish_ai_tutor.db.repositories.article_repo import ArticleRepository
from swedish_ai_tutor.db.repositories.phrase_repo import (
    PhraseRepository,
    is_reviewable_phrase,
)
from swedish_ai_tutor.db.tables import NotionPageScanRecord
from swedish_ai_tutor.prompts import load_prompt, render_prompt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BoldPhraseCandidate:
    """One bold expression and the surrounding Notion block text."""

    phrase: str
    context: str
    episode_id: int


class EnrichedNotionPhrase(BaseModel):
    """Minimal card details generated in one batched API response."""

    phrase: str
    meaning: str
    pattern_type: str
    context_chinese: str


class NotionPhraseScanResult(BaseModel):
    """Summary returned to pipeline logging."""

    checked_pages: int = 0
    scanned_pages: int = 0
    bold_candidates: int = 0
    already_known: int = 0
    imported: int = 0
    openai_calls: int = 0


class NotionPhraseScanner:
    """Scan only changed tutor pages and batch-enrich genuinely new phrases."""

    def __init__(
        self,
        session: Session,
        notion_api_key: str,
        openai_api_key: str,
        openai_model: str,
        *,
        notion_client: NotionClient | None = None,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        self._session = session
        self._notion = notion_client or NotionClient(auth=notion_api_key)
        self._openai = openai_client or AsyncOpenAI(api_key=openai_api_key)
        self._model = openai_model
        self._phrase_repo = PhraseRepository(session)
        self._template = load_prompt("v1", "notion_phrase_enrichment")

    async def scan(self) -> NotionPhraseScanResult:
        """Import new bold phrases, using zero OpenAI calls when none are new."""
        articles = ArticleRepository(self._session).get_notion_pages()
        article_by_page = {
            _normalize_page_id(article.notion_page_id or ""): article
            for article in articles
        }
        article_by_page.pop("", None)
        page_metadata = await self._search_accessible_pages()
        result = NotionPhraseScanResult(checked_pages=len(article_by_page))
        candidates: list[BoldPhraseCandidate] = []
        scans_to_update: list[tuple[str, str]] = []

        for page_id, article in article_by_page.items():
            metadata = page_metadata.get(page_id)
            if metadata is None:
                continue
            edited = str(metadata.get("last_edited_time", ""))
            cached = self._session.get(NotionPageScanRecord, page_id)
            if cached is not None and cached.last_edited_time == edited:
                continue
            blocks = await self._list_blocks_recursively(page_id)
            result.scanned_pages += 1
            for block in blocks:
                candidates.extend(_bold_candidates(block, article.episode_id))
            scans_to_update.append((page_id, edited))

        unique: dict[str, BoldPhraseCandidate] = {}
        for candidate in candidates:
            normalized = " ".join(candidate.phrase.lower().split())
            if is_reviewable_phrase(normalized) and _looks_swedish(normalized):
                unique.setdefault(normalized, candidate)
        result.bold_candidates = len(unique)
        new_candidates: list[BoldPhraseCandidate] = []
        for candidate in unique.values():
            if self._phrase_repo.get_by_phrase(candidate.phrase) is not None:
                result.already_known += 1
            else:
                new_candidates.append(candidate)

        if new_candidates:
            enriched = await self._enrich_batch(new_candidates)
            result.openai_calls = 1
            by_phrase = {item.phrase.casefold(): item for item in enriched}
            for candidate in new_candidates:
                item = by_phrase.get(candidate.phrase.casefold())
                if item is None:
                    continue
                self._phrase_repo.upsert(
                    candidate.phrase,
                    item.meaning,
                    item.pattern_type,
                    {
                        "swedish": candidate.context,
                        "chinese": item.context_chinese,
                    },
                    candidate.episode_id,
                )
                result.imported += 1

        for page_id, edited in scans_to_update:
            record = self._session.get(NotionPageScanRecord, page_id)
            if record is None:
                record = NotionPageScanRecord(page_id=page_id, last_edited_time=edited)
                self._session.add(record)
            else:
                record.last_edited_time = edited
                record.scanned_at = datetime.now(UTC)
        self._session.commit()
        return result

    async def _search_accessible_pages(self) -> dict[str, dict[str, Any]]:
        """Fetch page edit timestamps with normally one Notion API request."""
        pages: dict[str, dict[str, Any]] = {}
        cursor: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "filter": {"property": "object", "value": "page"},
                "page_size": 100,
            }
            if cursor:
                kwargs["start_cursor"] = cursor
            response = await self._notion.search(**kwargs)
            for page in response.get("results", []):
                page_id = _normalize_page_id(str(page.get("id", "")))
                if page_id:
                    pages[page_id] = page
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
        return pages

    async def _list_blocks_recursively(self, parent_id: str) -> list[dict[str, Any]]:
        """Retrieve all nested blocks under one changed lesson page."""
        blocks: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            kwargs: dict[str, Any] = {"page_size": 100}
            if cursor:
                kwargs["start_cursor"] = cursor
            response = await self._notion.blocks.children.list(
                block_id=parent_id, **kwargs
            )
            page_blocks = response.get("results", [])
            blocks.extend(page_blocks)
            for block in page_blocks:
                if block.get("has_children") and block.get("id"):
                    blocks.extend(
                        await self._list_blocks_recursively(str(block["id"]))
                    )
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
        return blocks

    async def _enrich_batch(
        self, candidates: list[BoldPhraseCandidate]
    ) -> list[EnrichedNotionPhrase]:
        """Complete every new phrase in a single OpenAI request."""
        phrase_input = "\n".join(
            f'- phrase: "{item.phrase}"\n  context: "{item.context[:500]}"'
            for item in candidates
        )
        prompt = render_prompt(self._template, phrases=phrase_input)
        response = await self._openai.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise Swedish teacher. Return JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content
        if not content:
            return []
        decoded = json.loads(content)
        return [
            EnrichedNotionPhrase.model_validate(item)
            for item in decoded.get("phrases", [])
        ]


def _normalize_page_id(value: str) -> str:
    """Extract a comparable 32-character Notion page ID from a URL or UUID."""
    compact = re.sub(r"[^0-9a-fA-F]", "", value.rsplit("-", 1)[-1])
    if len(compact) < 32:
        compact = re.sub(r"[^0-9a-fA-F]", "", value)
    return compact[-32:].lower() if len(compact) >= 32 else ""


def _bold_candidates(
    block: dict[str, Any], episode_id: int
) -> list[BoldPhraseCandidate]:
    """Extract adjacent bold spans and retain their surrounding block text."""
    block_type = str(block.get("type", ""))
    payload = block.get(block_type, {})
    rich_text = payload.get("rich_text", []) if isinstance(payload, dict) else []
    if not isinstance(rich_text, list):
        return []
    context = "".join(_plain_text(item) for item in rich_text).strip()
    results: list[BoldPhraseCandidate] = []
    bold_parts: list[str] = []
    for item in [*rich_text, None]:
        is_bold = bool(
            isinstance(item, dict) and item.get("annotations", {}).get("bold")
        )
        if is_bold and item is not None:
            bold_parts.append(_plain_text(item))
            continue
        if bold_parts:
            phrase = "".join(bold_parts).strip(" •—–-:;,.!?*\n\t")
            if phrase:
                results.append(BoldPhraseCandidate(phrase, context, episode_id))
            bold_parts = []
    return results


def _plain_text(item: object) -> str:
    """Read Notion rich-text content across API response variants."""
    if not isinstance(item, dict):
        return ""
    return str(item.get("plain_text") or item.get("text", {}).get("content", ""))


def _looks_swedish(value: str) -> bool:
    """Avoid importing bold Chinese notes, emoji, or punctuation as phrases."""
    return bool(re.search(r"[a-zåäö]", value, re.IGNORECASE))
