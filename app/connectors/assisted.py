from app.connectors.base import Connector


class AssistedConnector(Connector):
    key = "assisted"

    def build_assist_pack(self, rendition, destination):
        links = rendition.get("links", [])

        checklist = [
            "Read the community rules: "
            + (destination.get("rules_url") or "(no rules URL on file)")
        ]

        cap = destination.get("frequency_cap_per_week")
        if cap is not None:
            checklist.append(
                f"Post at most {cap} time(s) per week here. "
                "Check you have not already."
            )

        if not destination.get("self_promo_allowed", 1):
            checklist.append(
                "Self-promotion is NOT allowed. "
                "Post as a discussion, not an advert."
            )

        policy = destination.get("link_policy", "allowed")
        if policy == "none":
            checklist.append("Links are NOT allowed. Remove them.")
        elif policy == "limit_1":
            checklist.append("Only one link is allowed.")

        if destination.get("disclosure_required"):
            checklist.append("Add the AI-content disclosure line.")

        checklist.append(
            "After posting, paste the live URL back into IncuBrix."
        )

        content = rendition.get("title", "") + "\n\n" + rendition.get("body", "")
        if links:
            content += "\n\n" + "\n".join(links)

        return {
            "files": [
                {
                    "name": "post.md",
                    "content": content,
                }
            ],
            "caption": rendition.get("title", ""),
            "deep_link": (
                destination.get("submit_url")
                or destination.get("url", "")
            ),
            "checklist": checklist,
        }

    def publish(self, rendition, destination, connection, idempotency_key):
        return {
            "platform_post_id": f"assist-{idempotency_key}",
            "live_url": None,
            "status": "assist_pending",
        }

    def get_status(self, platform_post_id, connection):
        return {"status": "assist_pending", "live_url": None}

    def delete(self, platform_post_id, connection):
        return {"deleted": True}
