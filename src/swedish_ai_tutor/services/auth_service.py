"""Local account authentication with salted password hashes and opaque sessions."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from swedish_ai_tutor.db.tables import UserRecord, UserWordProgress, WebSessionRecord, WordRecord

SESSION_DAYS = 30


def _normalize_username(username: str) -> str:
    """Normalize and validate a local username."""
    normalized = username.strip().lower()
    if not 3 <= len(normalized) <= 50:
        raise ValueError("Username must contain 3–50 characters.")
    if not all(character.isalnum() or character in {"-", "_"} for character in normalized):
        raise ValueError("Username may contain only letters, numbers, hyphens, and underscores.")
    return normalized


def _password_digest(password: str, salt: bytes) -> str:
    """Derive a password digest using the standard-library scrypt KDF."""
    return hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    ).hex()


def _token_digest(token: str) -> str:
    """Hash an opaque session token before database storage."""
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    """Manage local users and browser sessions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def has_users(self) -> bool:
        """Return whether initial account setup is complete."""
        count = self._session.scalar(select(func.count()).select_from(UserRecord))
        return bool(count)

    def create_user(
        self,
        username: str,
        display_name: str,
        password: str,
        *,
        inherit_legacy_progress: bool = False,
    ) -> UserRecord:
        """Create a learner and optionally migrate existing legacy progress."""
        normalized = _normalize_username(username)
        name = display_name.strip()
        if not 1 <= len(name) <= 100:
            raise ValueError("Display name must contain 1–100 characters.")
        if len(password) < 8:
            raise ValueError("Password must contain at least 8 characters.")
        if self._session.scalar(select(UserRecord).where(UserRecord.username == normalized)):
            raise ValueError("That username already exists.")

        salt = secrets.token_bytes(16)
        user = UserRecord(
            username=normalized,
            display_name=name,
            password_salt=salt.hex(),
            password_hash=_password_digest(password, salt),
        )
        self._session.add(user)
        self._session.flush()

        if inherit_legacy_progress:
            now = datetime.now(UTC)
            words = self._session.scalars(select(WordRecord)).all()
            for word in words:
                if word.interval == 0 and word.repetitions == 0 and not word.mastered:
                    continue
                self._session.add(UserWordProgress(
                    user_id=user.id,
                    word_id=word.id,
                    mastered=word.mastered,
                    next_review=word.next_review,
                    ease_factor=word.ease_factor,
                    interval=word.interval,
                    repetitions=word.repetitions,
                    first_reviewed_at=now,
                    last_reviewed_at=now,
                ))
        self._session.commit()
        self._session.refresh(user)
        return user

    def authenticate(self, username: str, password: str) -> UserRecord | None:
        """Verify credentials without revealing which value was incorrect."""
        try:
            normalized = _normalize_username(username)
        except ValueError:
            return None
        user = self._session.scalar(select(UserRecord).where(UserRecord.username == normalized))
        if user is None:
            return None
        candidate = _password_digest(password, bytes.fromhex(user.password_salt))
        return user if hmac.compare_digest(candidate, user.password_hash) else None

    def create_session(self, user: UserRecord) -> str:
        """Create and return a new opaque browser token."""
        token = secrets.token_urlsafe(32)
        self._session.add(WebSessionRecord(
            user_id=user.id,
            token_hash=_token_digest(token),
            expires_at=datetime.now(UTC) + timedelta(days=SESSION_DAYS),
        ))
        self._session.commit()
        return token

    def user_for_token(self, token: str | None) -> UserRecord | None:
        """Resolve a non-expired session token to its learner."""
        if not token:
            return None
        now = datetime.now(UTC).replace(tzinfo=None)
        record = self._session.scalar(
            select(WebSessionRecord).where(WebSessionRecord.token_hash == _token_digest(token))
        )
        if record is None or record.expires_at <= now:
            if record is not None:
                self._session.delete(record)
                self._session.commit()
            return None
        return self._session.get(UserRecord, record.user_id)

    def delete_session(self, token: str | None) -> None:
        """Revoke one browser session."""
        if token:
            self._session.execute(
                delete(WebSessionRecord).where(WebSessionRecord.token_hash == _token_digest(token))
            )
            self._session.commit()
