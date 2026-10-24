
from datetime import datetime, timedelta, timezone

from app.rules import evaluate


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def dest(**over):
    base = {
        "frequency_cap_per_week": None,
        "self_promo_allowed": 1,
        "link_policy": "allowed",
        "disclosure_required": 0,
    }
    base.update(over)
    return base


def test_clean_post_is_allowed():
    decision = evaluate(dest(), {"title": "Hi"}, [], NOW)

    assert decision.allowed
    assert decision.action == "allow"


def test_weekly_cap_reschedules_post():
    earlier = [NOW - timedelta(days=2)]

    decision = evaluate(
        dest(frequency_cap_per_week=1),
        {"title": "Hi"},
        earlier,
        NOW,
    )

    assert decision.action == "reschedule"
    assert decision.violations[0].code == "DEST_RULE_FREQUENCY_CAP"
    assert decision.retry_after == (
        earlier[0] + timedelta(days=7)
    ).isoformat()


def test_old_post_does_not_count():
    earlier = [NOW - timedelta(days=9)]

    decision = evaluate(
        dest(frequency_cap_per_week=1),
        {"title": "Hi"},
        earlier,
        NOW,
    )

    assert decision.allowed


def test_self_promotion_is_blocked():
    decision = evaluate(
        dest(self_promo_allowed=0),
        {"title": "Buy", "is_promotional": True},
        [],
        NOW,
    )

    assert decision.action == "block"
    assert decision.violations[0].code == "DEST_RULE_SELF_PROMO"


def test_links_blocked_when_policy_is_none():
    decision = evaluate(
        dest(link_policy="none"),
        {"title": "Example", "links": ["https://a.com"]},
        [],
        NOW,
    )

    assert decision.action == "block"


def test_ai_disclosure_is_required():
    post = {
        "title": "Example",
        "ai_generated": True,
        "ai_disclosure_included": False,
    }

    decision = evaluate(
        dest(disclosure_required=1),
        post,
        [],
        NOW,
    )

    assert decision.violations[0].code == "DEST_RULE_AI_DISCLOSURE"

    post["ai_disclosure_included"] = True

    decision = evaluate(dest(disclosure_required=1), post, [], NOW)

    assert decision.allowed

def test_weekly_cap_blocks_when_two_posts_exist():
    earlier = [
        NOW - timedelta(days=2),
        NOW - timedelta(days=1),
    ]
    d = evaluate(
        dest(frequency_cap_per_week=2),
        {"title": "Third post"},
        earlier,
        NOW,
    )
    assert d.allowed is False
    assert d.action == "reschedule"
    assert d.violations[0].code == "DEST_RULE_FREQUENCY_CAP"
