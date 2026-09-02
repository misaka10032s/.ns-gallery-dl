from __future__ import annotations

from app.storage.db import execute, fetch_one


def delete_state(domain: str) -> bool:
    """Remove `domain`'s cooldown row, if any. Returns True if a row existed
    and was removed, False if there was nothing to clear (a plain
    get-then-delete: this is a rare, owner-triggered action, not a hot path,
    so the extra round trip to report whether anything actually changed is
    worth it over a blind unconditional DELETE)."""
    existing = get_state(domain)
    execute("DELETE FROM auth_cooldown WHERE domain = ?", (domain,))
    return existing is not None


def get_state(domain: str) -> dict | None:
    row = fetch_one(
        "SELECT domain, cooldown_until, last_classified_error, updated_at FROM auth_cooldown WHERE domain = ?",
        (domain,),
    )
    return dict(row) if row else None


def set_state(domain: str, cooldown_until: str, last_classified_error: str, updated_at: str) -> None:
    execute(
        """
        INSERT INTO auth_cooldown (domain, cooldown_until, last_classified_error, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(domain) DO UPDATE SET
            cooldown_until = excluded.cooldown_until,
            last_classified_error = excluded.last_classified_error,
            updated_at = excluded.updated_at
        """,
        (domain, cooldown_until, last_classified_error, updated_at),
    )
