import json
import os


def load_vk_config() -> dict:
    """
    Load VK credentials from environment or config.json.

    Environment variables take precedence so the same scripts can run both:
    - locally via config.json
    - in GitHub Actions via repository secrets
    """
    cfg = {}
    if os.path.exists("config.json"):
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)

    token = os.environ.get("VK_TOKEN") or cfg.get("vk_token")
    owner_id = os.environ.get("VK_OWNER_ID") or cfg.get("owner_id")
    community = os.environ.get("VK_COMMUNITY") or cfg.get("community")

    if token is None or owner_id is None:
        raise RuntimeError(
            "VK config is missing. Set VK_TOKEN and VK_OWNER_ID env vars or provide config.json."
        )

    owner_id = int(owner_id)
    if not community:
        community = f"club{abs(owner_id)}"

    return {
        "vk_token": token,
        "owner_id": owner_id,
        "community": community,
        "group_id": abs(owner_id),
    }
