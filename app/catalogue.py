
import csv
import io
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.db import get_conn

ALLOWED_PLATFORMS = {
    "discourse", "lemmy", "devto", "ghost", "webhook", "assisted"
}
LINK_POLICIES = {"allowed", "none", "limit_1"}
REQUIRED = ["name", "url", "platform_key", "connector_key"]
TRUE_VALUES = {"1", "true", "yes", "y"}


def normalize_url(url: str) -> str:
    p = urlparse(url.strip())
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host + p.path.rstrip("/")


def _bool(value, default):
    if value is None or value == "":
        return default
    return str(value).strip().lower() in TRUE_VALUES


def _int(value):
    if value is None or value == "":
        return None
    return int(value)


def validate_row(raw: dict):
    """Returns (clean_row, errors). Empty errors means the row is valid."""
    row = {
        (k or "").strip().lstrip("\ufeff"): (
            str(v).strip() if v is not None else ""
        )
        for k, v in raw.items()
    }
    errors = []

    for field in REQUIRED:
        if not row.get(field):
            errors.append(f"missing {field}")

    url = row.get("url", "")
    if url:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            errors.append("invalid url")

    platform = row.get("platform_key", "")
    if platform and platform not in ALLOWED_PLATFORMS:
        errors.append(f"unknown platform_key '{platform}'")

    policy = row.get("link_policy") or "allowed"
    if policy not in LINK_POLICIES:
        errors.append(f"invalid link_policy '{policy}'")
    row["link_policy"] = policy

    for numeric in (
        "frequency_cap_per_week", "est_audience", "relevance_score"
    ):
        try:
            row[numeric] = _int(row.get(numeric))
        except ValueError:
            errors.append(f"{numeric} must be a whole number")
            row[numeric] = None

    score = row.get("relevance_score")
    if score is not None and not 1 <= score <= 5:
        errors.append("relevance_score must be 1 to 5")

    row["self_promo_allowed"] = _bool(
        row.get("self_promo_allowed"), True
    )
    row["disclosure_required"] = _bool(
        row.get("disclosure_required"), False
    )
    row["automation_allowed"] = _bool(
        row.get("automation_allowed"), True
    )

    return row, errors


INSERT_SQL = """
INSERT INTO destinations
(name, url, normalized_url, platform_key, connector_key, surface, category,
 audience_tags, language, geo, est_audience, rules_url, frequency_cap_per_week,
 self_promo_allowed, link_policy, disclosure_required, automation_allowed,
 relevance_score, relevance_reason)
VALUES
(:name, :url, :normalized_url, :platform_key, :connector_key, :surface, :category,
 :audience_tags, :language, :geo, :est_audience, :rules_url, :frequency_cap_per_week,
 :self_promo_allowed, :link_policy, :disclosure_required, :automation_allowed,
 :relevance_score, :relevance_reason)
"""

OPTIONAL_TEXT = [
    "surface", "category", "audience_tags", "geo",
    "rules_url", "relevance_reason"
]


def _insert(conn, row):
    data = dict(row)
    data["normalized_url"] = normalize_url(row["url"])
    data["language"] = row.get("language") or "en"

    for field in OPTIONAL_TEXT:
        data[field] = row.get(field, "")

    data.setdefault("est_audience", None)
    cur = conn.execute(INSERT_SQL, data)
    return cur.lastrowid


def add_destination(raw: dict):
    """Returns ('created', id), ('duplicate', None), or ('invalid', errors)."""
    row, errors = validate_row(raw)
    if errors:
        return "invalid", errors

    conn = get_conn()
    try:
        new_id = _insert(conn, row)
        conn.commit()
        return "created", new_id
    except sqlite3.IntegrityError:
        conn.rollback()
        return "duplicate", None
    finally:
        conn.close()


def import_csv(text: str):
    """Import destinations from CSV text, handling UTF-8 BOM headers."""
    text = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))

    report = {
        "rows_total": 0,
        "imported": 0,
        "duplicates": 0,
        "invalid": 0,
        "errors": [],
    }

    conn = get_conn()
    try:
        for line_no, raw in enumerate(reader, start=2):
            report["rows_total"] += 1
            row, errors = validate_row(raw)

            if errors:
                report["invalid"] += 1
                report["errors"].append({
                    "row": line_no,
                    "errors": errors,
                })
                continue

            try:
                _insert(conn, row)
                report["imported"] += 1
            except sqlite3.IntegrityError:
                report["duplicates"] += 1
                report["errors"].append({
                    "row": line_no,
                    "errors": ["duplicate destination"],
                })

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return report


def get_destination(dest_id: int):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM destinations WHERE id = ?", (dest_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_destinations():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM destinations ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def record_post(
    dest_id: int,
    status: str = "published",
    when: datetime | None = None,
):
    when = when or datetime.now(timezone.utc)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO posts (destination_id, status, posted_at) "
            "VALUES (?, ?, ?)",
            (dest_id, status, when.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def recent_post_times(dest_id: int):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT posted_at FROM posts "
            "WHERE destination_id = ? "
            "AND status IN ('published','pending')",
            (dest_id,),
        ).fetchall()
        return [datetime.fromisoformat(row["posted_at"]) for row in rows]
    finally:
        conn.close()


UPDATABLE = {"enabled", "level", "last_certified_at"}


def update_destination(dest_id: int, **fields):
    if not fields or set(fields) - UPDATABLE:
        raise ValueError(f"can only update {sorted(UPDATABLE)}")

    sets = ", ".join(f"{name} = ?" for name in fields)
    conn = get_conn()
    try:
        conn.execute(
            f"UPDATE destinations SET {sets} WHERE id = ?",
            (*fields.values(), dest_id),
        )
        conn.commit()
    finally:
        conn.close()
