"""Tests for safe merging of inflected vocabulary duplicates."""

import json
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


def test_restores_comparative_adjective_and_complete_morphology(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = get_session_factory(engine)
    malformed = {
        "type": "adjective",
        "en_form": "billigare",
        "ett_form": "billigare",
        "plural_definite": "billigaste",
        "comparative": "billigare",
        "superlative": "billigaste",
    }
    with factory() as session:
        WordRepository(session).create("billigare", "adj", "更便宜的", malformed)

    result = dedupe_vocabulary(db_path)

    assert result.renamed == 1
    with factory() as session:
        record = session.scalar(select(WordRecord))
        assert record is not None
        assert record.word == "billig"
        assert json.loads(record.morphology or "{}") == {
            "type": "adjective",
            "en_form": "billig",
            "ett_form": "billigt",
            "plural_definite": "billiga",
            "comparative": "billigare",
            "superlative": "billigast",
        }


def test_restores_irregular_comparative_and_merges_positive(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    engine = create_db_engine(db_path)
    init_db(engine)
    factory = get_session_factory(engine)
    correct = {
        "type": "adjective",
        "en_form": "stor",
        "ett_form": "stort",
        "plural_definite": "stora",
        "comparative": "större",
        "superlative": "störst",
    }
    malformed = {**correct, "en_form": "större", "plural_definite": "större"}
    with factory() as session:
        repo = WordRepository(session)
        repo.create("stor", "adj", "大的", correct)
        repo.create("större", "adj", "更大的", malformed)

    result = dedupe_vocabulary(db_path)

    assert result.merged == 1
    with factory() as session:
        records = list(session.scalars(select(WordRecord)))
        assert len(records) == 1
        assert records[0].word == "stor"
        assert records[0].frequency == 2
        assert json.loads(records[0].morphology or "{}")["plural_definite"] == "stora"
