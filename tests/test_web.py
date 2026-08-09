"""Tests for the mobile vocabulary review web application."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from swedish_ai_tutor.config import Settings
from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.tables import (
    PhraseRecord,
    UserPhraseProgress,
    UserWordProgress,
    WordRecord,
)
from swedish_ai_tutor.web.app import create_app


def _settings(db_path: Path) -> Settings:
    return Settings(
        openai_api_key="test",
        notion_api_key="test",
        notion_parent_page_id="test",
        db_path=db_path,
        data_dir=db_path.parent,
    )


def _add_word(db_path: Path, *, due: bool = True) -> WordRecord:
    engine = create_db_engine(db_path)
    init_db(engine)
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        word = WordRecord(
            word="utreda",
            pos="verb",
            meaning="调查",
            next_review=datetime.now(UTC) - timedelta(days=1) if due else None,
            morphology=(
                '{"type":"verb","imperative":"utred","infinitive":"utreda",'
                '"present":"utreder","past":"utredde","supine":"utrett"}'
            ),
            examples=(
                '{"swedish":"Polisen ska utreda händelsen.","chinese":"警方将调查这一事件。"}'
            ),
        )
        session.add(word)
        session.commit()
        session.refresh(word)
        session.expunge(word)
        return word


def _register_owner(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "owner",
            "display_name": "Owner",
            "password": "correct-horse",
        },
    )
    assert response.status_code == 201


def _client(db_path: Path, *, register: bool = True) -> TestClient:
    client = TestClient(create_app(_settings(db_path)), base_url="https://tutor.test")
    if register:
        _register_owner(client)
    return client


def test_session_returns_due_words_and_stats(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    word = _add_word(db_path)
    client = _client(db_path)

    response = client.get("/api/session?limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"]["due"] == 0
    assert payload["stats"]["new"] == 1
    assert payload["items"][0]["id"] == word.id
    assert payload["items"][0]["meaning"] == "调查"
    assert payload["items"][0]["morphology"]["present"] == "utreder"
    assert payload["items"][0]["example"] == {
        "swedish": "Polisen ska utreda händelsen.",
        "chinese": "警方将调查这一事件。",
    }


def test_lesson_player_pages_and_api_require_authentication(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    client = _client(db_path, register=False)

    assert client.get("/lessons").status_code == 200
    assert client.get("/lessons/123").status_code == 200
    assert client.get("/api/lessons").status_code == 401
    assert client.get("/api/lessons/123").status_code == 401


def test_shadow_pause_does_not_force_article_scroll(tmp_path: Path) -> None:
    client = _client(tmp_path / "vocabulary.db")

    page = client.get("/lessons/123").text

    pause_body = page.split("function beginShadowPause(index){", 1)[1].split(
        "function ensureSentenceVisible", 1
    )[0]
    assert "ensureSentenceVisible" not in pause_body
    assert "buttonRect.top<safeTop" in page
    assert "buttonRect.bottom>safeBottom" in page


def test_lesson_list_api_uses_saved_lesson_files(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    lessons_dir = tmp_path / "lessons"
    lessons_dir.mkdir()
    source = Path(__file__).parent / "fixtures" / "sample_lesson.json"
    if source.exists():
        (lessons_dir / "lesson_sample.json").write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )
    client = _client(db_path)

    response = client.get("/api/lessons")

    assert response.status_code == 200
    assert "lessons" in response.json()


def test_review_updates_the_shared_database(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    word = _add_word(db_path)
    client = _client(db_path)

    response = client.post(f"/api/words/{word.id}/review", json={"quality": 4})

    assert response.status_code == 200
    assert response.json()["interval"] == 1
    engine = create_db_engine(db_path)
    with get_session_factory(engine)() as session:
        saved = session.execute(
            select(UserWordProgress).where(UserWordProgress.word_id == word.id)
        ).scalar_one()
        assert saved.repetitions == 1
        assert saved.interval == 1


def test_stats_supports_session_start_screen(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    _add_word(db_path)
    client = _client(db_path)

    response = client.get("/api/stats")

    assert response.status_code == 200
    assert response.json()["due"] == 0
    assert response.json()["new"] == 1


def test_word_cannot_advance_twice_before_calendar_due_date(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    word = _add_word(db_path)
    client = _client(db_path)

    first = client.post(f"/api/words/{word.id}/review", json={"quality": 0})
    second = client.post(f"/api/words/{word.id}/review", json={"quality": 5})

    assert first.status_code == 200
    assert first.json()["repetitions"] == 0
    assert second.status_code == 409
    assert second.json()["detail"] == "This word was already reviewed and is not due yet."

    engine = create_db_engine(db_path)
    with get_session_factory(engine)() as session:
        saved = session.execute(
            select(UserWordProgress).where(UserWordProgress.word_id == word.id)
        ).scalar_one()
        assert saved.repetitions == 0
        assert saved.interval == 1

    next_session = client.get("/api/session?limit=20")
    assert next_session.status_code == 200
    assert next_session.json()["items"] == []
    assert next_session.json()["stats"]["new"] == 0


def test_review_validation_and_missing_word(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    client = _client(db_path)

    assert client.post("/api/words/999/review", json={"quality": 4}).status_code == 404
    assert client.post("/api/words/999/review", json={"quality": 8}).status_code == 422


def test_confirmed_delete_removes_word_and_all_review_progress(tmp_path: Path) -> None:
    """Authenticated deletion removes the shared card and attached learner state."""
    db_path = tmp_path / "vocabulary.db"
    word = _add_word(db_path)
    client = _client(db_path)
    assert client.post(f"/api/words/{word.id}/review", json={"quality": 4}).status_code == 200

    response = client.delete(f"/api/words/{word.id}")

    assert response.status_code == 200
    assert response.json() == {"deleted": "utreda"}
    engine = create_db_engine(db_path)
    with get_session_factory(engine)() as session:
        assert session.get(WordRecord, word.id) is None
        assert session.scalar(
            select(UserWordProgress).where(UserWordProgress.word_id == word.id)
        ) is None


def test_delete_word_requires_login(tmp_path: Path) -> None:
    """The destructive endpoint cannot be called without a valid session."""
    db_path = tmp_path / "vocabulary.db"
    word = _add_word(db_path)
    client = _client(db_path, register=False)

    assert client.delete(f"/api/words/{word.id}").status_code == 401


def test_home_screen_assets_are_served(tmp_path: Path) -> None:
    client = _client(tmp_path / "vocabulary.db", register=False)

    page = client.get("/")
    manifest = client.get("/manifest.webmanifest")

    assert page.status_code == 200
    assert "Svenska varje dag" in page.text
    assert "Words in this session" in page.text
    assert "memory curve follows calendar due dates" in page.text
    assert "Från nyheterna · 新闻例句" in page.text
    assert manifest.status_code == 200
    assert manifest.json()["display"] == "standalone"


def test_phrase_session_and_review_have_independent_progress(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    engine = create_db_engine(db_path)
    init_db(engine)
    with get_session_factory(engine)() as session:
        phrase = PhraseRecord(
            phrase="ta fram ett förslag",
            meaning="提出一项建议",
            pattern_type="collocation",
            examples=(
                '{"swedish":"Regeringen ska ta fram ett förslag.","chinese":"政府将提出一项建议。"}'
            ),
        )
        session.add(phrase)
        session.commit()
        phrase_id = phrase.id
    client = _client(db_path)

    queue = client.get("/api/session?limit=10&kind=phrases")
    assert queue.status_code == 200
    assert queue.json()["items"][0]["phrase"] == "ta fram ett förslag"
    assert queue.json()["items"][0]["example"]["chinese"] == "政府将提出一项建议。"

    reviewed = client.post(f"/api/phrases/{phrase_id}/review", json={"quality": 4})
    assert reviewed.status_code == 200
    with get_session_factory(engine)() as session:
        progress = session.scalar(
            select(UserPhraseProgress).where(UserPhraseProgress.phrase_id == phrase_id)
        )
        assert progress is not None
        assert progress.interval == 1


def test_confirmed_phrase_delete_removes_shared_phrase_and_progress(
    tmp_path: Path,
) -> None:
    """Phrase deletion cleans its catalog row and every attached learner state."""
    db_path = tmp_path / "vocabulary.db"
    engine = create_db_engine(db_path)
    init_db(engine)
    with get_session_factory(engine)() as session:
        phrase = PhraseRecord(
            phrase="ta fram ett förslag",
            meaning="提出一项建议",
            pattern_type="collocation",
        )
        session.add(phrase)
        session.commit()
        phrase_id = phrase.id
    client = _client(db_path)
    assert client.post(
        f"/api/phrases/{phrase_id}/review", json={"quality": 4}
    ).status_code == 200

    response = client.delete(f"/api/phrases/{phrase_id}")

    assert response.status_code == 200
    assert response.json() == {"deleted": "ta fram ett förslag"}
    with get_session_factory(engine)() as session:
        assert session.get(PhraseRecord, phrase_id) is None
        assert session.scalar(
            select(UserPhraseProgress).where(
                UserPhraseProgress.phrase_id == phrase_id
            )
        ) is None


def test_delete_phrase_requires_login(tmp_path: Path) -> None:
    """Phrase deletion cannot bypass local-account authentication."""
    db_path = tmp_path / "vocabulary.db"
    engine = create_db_engine(db_path)
    init_db(engine)
    with get_session_factory(engine)() as session:
        phrase = PhraseRecord(
            phrase="ta fram ett förslag",
            meaning="提出一项建议",
            pattern_type="collocation",
        )
        session.add(phrase)
        session.commit()
        phrase_id = phrase.id
    client = _client(db_path, register=False)

    assert client.delete(f"/api/phrases/{phrase_id}").status_code == 401


def test_first_account_receives_existing_review_progress(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    word = _add_word(db_path)
    engine = create_db_engine(db_path)
    with get_session_factory(engine)() as session:
        saved = session.get(WordRecord, word.id)
        assert saved is not None
        saved.interval = 6
        saved.repetitions = 2
        saved.next_review = datetime.now(UTC) - timedelta(days=1)
        session.commit()

    client = _client(db_path)

    stats = client.get("/api/stats").json()
    queue = client.get("/api/session?limit=10").json()["items"]
    assert stats["due"] == 1
    assert stats["new"] == 0
    assert queue[0]["interval"] == 6
    assert len(list(tmp_path.glob("vocabulary.db.before-accounts-*.backup"))) == 1


def test_accounts_have_independent_memory_curves(tmp_path: Path) -> None:
    db_path = tmp_path / "vocabulary.db"
    word = _add_word(db_path)
    client = _client(db_path)
    assert client.post(f"/api/words/{word.id}/review", json={"quality": 4}).status_code == 200

    created = client.post(
        "/api/auth/register",
        json={
            "username": "husband",
            "display_name": "Husband",
            "password": "another-horse",
        },
    )
    assert created.status_code == 201
    assert client.post("/api/auth/logout").status_code == 204
    login = client.post(
        "/api/auth/login",
        json={"username": "husband", "password": "another-horse"},
    )
    assert login.status_code == 200

    husband_stats = client.get("/api/stats").json()
    husband_words = client.get("/api/session?limit=10").json()["items"]
    assert husband_stats["new"] == 1
    assert husband_stats["learning"] == 0
    assert husband_words[0]["id"] == word.id
    assert husband_words[0]["interval"] == 0


def test_auth_cookie_is_secure_and_review_routes_require_login(tmp_path: Path) -> None:
    client = _client(tmp_path / "vocabulary.db", register=False)
    assert client.get("/api/stats").status_code == 401

    response = client.post(
        "/api/auth/register",
        json={
            "username": "owner",
            "display_name": "Owner",
            "password": "correct-horse",
        },
    )

    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
