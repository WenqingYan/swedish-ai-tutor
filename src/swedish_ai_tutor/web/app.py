"""FastAPI application for private mobile vocabulary review."""

import json
import sqlite3
from collections.abc import Iterator  # noqa: TC003 - FastAPI inspects annotations
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from swedish_ai_tutor.config import Settings  # noqa: TC001 - FastAPI resolves annotations
from swedish_ai_tutor.db.engine import create_db_engine, get_session_factory, init_db
from swedish_ai_tutor.db.tables import (  # noqa: TC001 - FastAPI resolves annotations
    UserRecord,
    UserWordProgress,
    WordRecord,
)
from swedish_ai_tutor.services.auth_service import SESSION_DAYS, AuthService
from swedish_ai_tutor.services.user_vocabulary_service import UserVocabularyService


class ReviewRequest(BaseModel):
    """A learner's recall rating for one word."""

    quality: int = Field(ge=0, le=5)


class LoginRequest(BaseModel):
    """Credentials submitted by an existing learner."""

    username: str
    password: str


class RegisterRequest(LoginRequest):
    """Details for creating a local learner account."""

    display_name: str


def _backup_database(db_path: Path) -> Path:
    """Create a consistent SQLite backup before the account migration."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.with_name(f"{db_path.name}.before-accounts-{timestamp}.backup")
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination)
    return backup_path


def _word_payload(
    word: WordRecord, progress: UserWordProgress | None = None
) -> dict[str, Any]:
    """Serialize the fields needed by the review interface."""
    morphology: dict[str, Any] | None = None
    example: dict[str, str] | None = None
    if word.morphology:
        try:
            decoded = json.loads(word.morphology)
            if isinstance(decoded, dict):
                morphology = decoded
        except json.JSONDecodeError:
            pass
    if word.examples:
        try:
            decoded_example = json.loads(word.examples)
            if isinstance(decoded_example, dict):
                swedish = str(decoded_example.get("swedish", "")).strip()
                chinese = str(decoded_example.get("chinese", "")).strip()
                if swedish or chinese:
                    example = {"swedish": swedish, "chinese": chinese}
        except json.JSONDecodeError:
            pass
    return {
        "id": word.id,
        "word": word.word,
        "pos": word.pos,
        "meaning": word.meaning,
        "frequency": word.frequency,
        "interval": progress.interval if progress else 0,
        "morphology": morphology,
        "example": example,
    }


def create_app(settings: Settings) -> FastAPI:
    """Create a web application backed by the configured SQLite database."""
    engine = create_db_engine(settings.db_path)
    init_db(engine)
    session_factory = get_session_factory(engine)
    app = FastAPI(
        title="Svenska varje dag",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def get_session() -> Iterator[Session]:
        """Provide one database session per request."""
        with session_factory() as session:
            yield session

    SessionDependency = Annotated[Session, Depends(get_session)]  # noqa: N806

    def get_current_user(
        session: SessionDependency,
        tutor_session: Annotated[str | None, Cookie()] = None,
    ) -> UserRecord:
        """Require a valid opaque browser session."""
        user = AuthService(session).user_for_token(tutor_session)
        if user is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        return user

    UserDependency = Annotated[UserRecord, Depends(get_current_user)]  # noqa: N806

    def set_session_cookie(response: Response, token: str) -> None:
        """Attach the authentication token with hardened browser attributes."""
        response.set_cookie(
            key="tutor_session",
            value=token,
            max_age=SESSION_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=settings.web_secure_cookies,
            samesite="strict",
            path="/",
        )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        """Serve the mobile review application shell."""
        return files("swedish_ai_tutor.web.static").joinpath("index.html").read_text()

    @app.get("/manifest.webmanifest")
    def manifest() -> Response:
        """Describe the site for iPhone Home Screen installation."""
        payload = {
            "name": "Svenska varje dag",
            "short_name": "Svenska",
            "description": "Daily Swedish vocabulary review",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#f6f1e8",
            "theme_color": "#173f35",
        }
        return Response(json.dumps(payload), media_type="application/manifest+json")

    @app.get("/api/auth/status")
    def auth_status(
        session: SessionDependency,
        tutor_session: Annotated[str | None, Cookie()] = None,
    ) -> dict[str, Any]:
        """Return setup and sign-in state without exposing credentials."""
        auth = AuthService(session)
        user = auth.user_for_token(tutor_session)
        return {
            "setup_required": not auth.has_users(),
            "authenticated": user is not None,
            "user": (
                {"username": user.username, "display_name": user.display_name}
                if user else None
            ),
        }

    @app.post("/api/auth/register", status_code=201)
    def register(
        registration: RegisterRequest,
        response: Response,
        session: SessionDependency,
        tutor_session: Annotated[str | None, Cookie()] = None,
    ) -> dict[str, Any]:
        """Bootstrap the owner or let a signed-in learner add an account."""
        auth = AuthService(session)
        first_user = not auth.has_users()
        if not first_user and auth.user_for_token(tutor_session) is None:
            raise HTTPException(status_code=401, detail="Sign in to add an account.")
        try:
            if first_user:
                _backup_database(settings.db_path)
            user = auth.create_user(
                registration.username,
                registration.display_name,
                registration.password,
                inherit_legacy_progress=first_user,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if first_user:
            set_session_cookie(response, auth.create_session(user))
        return {"username": user.username, "display_name": user.display_name}

    @app.post("/api/auth/login")
    def login(
        credentials: LoginRequest,
        response: Response,
        session: SessionDependency,
    ) -> dict[str, str]:
        """Authenticate a learner and issue a hardened session cookie."""
        auth = AuthService(session)
        user = auth.authenticate(credentials.username, credentials.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        set_session_cookie(response, auth.create_session(user))
        return {"username": user.username, "display_name": user.display_name}

    @app.post("/api/auth/logout", status_code=204)
    def logout(
        response: Response,
        session: SessionDependency,
        tutor_session: Annotated[str | None, Cookie()] = None,
    ) -> None:
        """Revoke the current browser session and clear its cookie."""
        AuthService(session).delete_session(tutor_session)
        response.delete_cookie(
            "tutor_session",
            secure=settings.web_secure_cookies,
            httponly=True,
            samesite="strict",
            path="/",
        )

    @app.get("/api/session")
    def review_session(
        session: SessionDependency,
        user: UserDependency,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, Any]:
        """Return statistics and today's due-first review queue."""
        service = UserVocabularyService(session, user.id)
        return {
            "stats": service.get_stats(),
            "words": [
                _word_payload(word, progress)
                for word, progress in service.get_review_queue(limit)
            ],
        }

    @app.get("/api/stats")
    def vocabulary_stats(
        session: SessionDependency, user: UserDependency
    ) -> dict[str, int]:
        """Return counts for the session-start screen."""
        return UserVocabularyService(session, user.id).get_stats()

    @app.post("/api/words/{word_id}/review")
    def submit_review(
        word_id: int,
        review: ReviewRequest,
        session: SessionDependency,
        user: UserDependency,
    ) -> dict[str, Any]:
        """Apply a review rating with the existing SM-2 scheduler."""
        service = UserVocabularyService(session, user.id)
        try:
            result = service.process_review(word_id, review.quality)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "next_review": result.next_review.isoformat(),
            "interval": result.interval,
            "repetitions": result.repetitions,
        }

    return app
