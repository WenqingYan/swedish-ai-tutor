"""Tests for safe merging of inflected vocabulary duplicates."""

from pathlib import Path

from sqlalchemy import select

from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.repositories.word_repo import WordRepository
from swedish_ai_tutor.db.tables import WordRecord
from swedish_ai_tutor.dedupe_vocabulary import dedupe_vocabulary


def test_merges_inflected_rows_and_creates_backup(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = get_session_factory(engine)
    morphology = {
        "type": "verb",
        "group": 1,
        "imperative": "berätta",
        "infinitive": "berätta",
        "present": "berättar",
        "past": "berättade",
        "supine": "berättat",
    }
    with factory() as session:
        repo = WordRepository(session)
        repo.create("berätta", "verb", "讲述", morphology, episode_id=1)
        repo.create("berättar", "verb", "讲述", morphology, episode_id=2)

    result = dedupe_vocabulary(db_path)

    assert result.backup_path.exists()
    assert result.merged == 1
    with factory() as session:
        records = list(session.scalars(select(WordRecord)))
        assert len(records) == 1
        assert records[0].word == "berätta"
        assert records[0].frequency == 2
