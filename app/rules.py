from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

WINDOW = timedelta(days=7)


@dataclass
class Violation:
    code: str
    reason: str


@dataclass
class Decision:
    allowed: bool
    action: str  # "allow" | "block" | "reschedule"
    violations: list = field(default_factory=list)
    retry_after: str | None = None

    def to_dict(self):
        return {
            "allowed": self.allowed,
            "action": self.action,
            "violations": [v.__dict__ for v in self.violations],
            "retry_after": self.retry_after,
        }


def evaluate(destination: dict, post: dict, recent_posts: list, now: datetime | None = None) -> Decision:
    """
    destination: a row from the catalogue
    post: {"title", "body", "links": [...], "is_promotional": bool,
           "ai_generated": bool, "ai_disclosure_included": bool}
    recent_posts: list of datetimes of earlier posts to this destination
    """
    now = now or datetime.now(timezone.utc)
    violations = []
    retry_after = None

    # 1. Frequency cap
    cap = destination.get("frequency_cap_per_week")
    if cap is not None:
        in_window = sorted(t for t in recent_posts if now - t < WINDOW)
        if len(in_window) >= cap:
            # the cap frees up when the post at this position ages out of the window
            frees_at = in_window[len(in_window) - cap] + WINDOW if cap > 0 else None
            retry_after = frees_at.isoformat() if frees_at else None
            violations.append(Violation(
                "DEST_RULE_FREQUENCY_CAP",
                f"Weekly cap of {cap} reached ({len(in_window)} posts in the last 7 days).",
            ))

    # 2. Self-promotion
    if post.get("is_promotional") and not destination.get("self_promo_allowed"):
        violations.append(Violation(
            "DEST_RULE_SELF_PROMO",
            "This destination does not allow self-promotion.",
        ))

    # 3. Link policy
    links = post.get("links") or []
    policy = destination.get("link_policy", "allowed")
    if policy == "none" and links:
        violations.append(Violation("DEST_RULE_LINKS", "This destination does not allow links."))
    elif policy == "limit_1" and len(links) > 1:
        violations.append(Violation("DEST_RULE_LINKS", "This destination allows at most 1 link."))

    # 4. AI disclosure
    if (destination.get("disclosure_required")
            and post.get("ai_generated")
            and not post.get("ai_disclosure_included")):
        violations.append(Violation(
            "DEST_RULE_AI_DISCLOSURE",
            "This destination requires AI-content disclosure and none was included.",
        ))

    if not violations:
        return Decision(True, "allow")

    only_frequency = all(v.code == "DEST_RULE_FREQUENCY_CAP" for v in violations)
    if only_frequency and retry_after:
        return Decision(False, "reschedule", violations, retry_after)
    return Decision(False, "block", violations)