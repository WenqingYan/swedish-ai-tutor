"""SM-2 spaced repetition algorithm.

Implementation of the SuperMemo 2 algorithm for scheduling vocabulary reviews.
Reference: https://www.supermemo.com/en/archives1990-2015/english/ol/sm2

Quality ratings:
    0 - Complete blackout, no recall at all
    1 - Wrong answer, but recognized after seeing it
    2 - Wrong answer, but seemed easy to recall after seeing it
    3 - Correct answer with serious difficulty
    4 - Correct answer with some hesitation
    5 - Perfect recall, no hesitation
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class ReviewResult:
    """Result of applying SM-2 after a review."""

    next_review: datetime
    ease_factor: float
    interval: int
    repetitions: int


def calculate_next_review(
    quality: int,
    repetitions: int,
    ease_factor: float,
    interval: int,
) -> ReviewResult:
    """Calculate next review date using the SM-2 algorithm.

    Args:
        quality: Rating 0-5 from the review session.
        repetitions: Number of consecutive successful reviews.
        ease_factor: Current ease factor (minimum 1.3).
        interval: Current interval in days.

    Returns:
        ReviewResult with updated scheduling state.

    Raises:
        ValueError: If quality is not 0-5.
    """
    if quality < 0 or quality > 5:
        msg = f"Quality must be 0-5, got {quality}"
        raise ValueError(msg)

    now = datetime.now(UTC)

    # Failed review (quality < 3): reset
    if quality < 3:
        new_repetitions = 0
        new_interval = 1
        # Reduce ease factor but keep minimum at 1.3
        new_ef = max(1.3, ease_factor - 0.2)
    else:
        # Successful review
        new_repetitions = repetitions + 1

        if new_repetitions == 1:
            new_interval = 1
        elif new_repetitions == 2:
            new_interval = 6
        else:
            new_interval = round(interval * ease_factor)

        # Update ease factor
        new_ef = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_ef = max(1.3, new_ef)

    next_review = now + timedelta(days=new_interval)

    return ReviewResult(
        next_review=next_review,
        ease_factor=round(new_ef, 2),
        interval=new_interval,
        repetitions=new_repetitions,
    )
