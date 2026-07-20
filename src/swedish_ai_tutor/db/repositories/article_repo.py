"""Repository for managing processed article records."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from swedish_ai_tutor.db.tables import ArticleRecord
from swedish_ai_tutor.models.episode import Episode


class ArticleRepository:
    """Data access layer for article/episode tracking.

    Handles deduplication — ensures each episode is only processed once.
    """

    def __init__(self, session: Session) -> None:
        """Initialize with a database session.

        Args:
            session: SQLAlchemy session for database operations.
        """
        self._session = session

    def exists(self, episode_id: int) -> bool:
        """Check if an episode has already been processed.

        Args:
            episode_id: SR episode ID to check.

        Returns:
            True if the episode is already in the database.
        """
        stmt = select(ArticleRecord).where(ArticleRecord.episode_id == episode_id)
        result = self._session.execute(stmt).scalar_one_or_none()
        return result is not None

    def create(self, episode: Episode, notion_page_id: str | None = None) -> ArticleRecord:
        """Record a processed episode.

        Args:
            episode: The episode that was processed.
            notion_page_id: Optional Notion page ID if export was successful.

        Returns:
            The created database record.
        """
        record = ArticleRecord(
            episode_id=episode.id,
            title=episode.title,
            publish_date=episode.publish_date,
            audio_url=episode.audio_url,
            notion_page_id=notion_page_id,
            status="completed" if notion_page_id else "pending_export",
        )
        self._session.add(record)
        self._session.commit()
        return record

    def update_notion_page(self, episode_id: int, notion_page_id: str) -> None:
        """Update the Notion page ID for a previously processed episode.

        Used when retrying a failed Notion export.

        Args:
            episode_id: SR episode ID.
            notion_page_id: Notion page ID from successful export.
        """
        stmt = select(ArticleRecord).where(ArticleRecord.episode_id == episode_id)
        record = self._session.execute(stmt).scalar_one_or_none()
        if record:
            record.notion_page_id = notion_page_id
            record.status = "completed"
            self._session.commit()

    def get_pending_exports(self) -> list[ArticleRecord]:
        """Get all episodes that were processed but not yet exported to Notion.

        Returns:
            List of article records with pending export status.
        """
        stmt = select(ArticleRecord).where(ArticleRecord.status == "pending_export")
        return list(self._session.execute(stmt).scalars().all())

    def get_by_date(self, date: datetime) -> ArticleRecord | None:
        """Get article processed for a specific date.

        Args:
            date: Target date to look up.

        Returns:
            The article record, or None if not found.
        """
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        stmt = select(ArticleRecord).where(
            ArticleRecord.publish_date.between(start, end)
        )
        return self._session.execute(stmt).scalar_one_or_none()
