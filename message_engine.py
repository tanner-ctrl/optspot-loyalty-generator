import os
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv()

_client = None


def is_demo_mode() -> bool:
    """Return True when the app should use canned demo messages instead of the API."""
    if os.getenv("DEMO_MODE", "").lower() == "true":
        return True
    key = os.getenv("ANTHROPIC_API_KEY", "")
    return not key or key == "your_key_here"


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _load_prompt(message_type: str) -> str:
    path = Path(__file__).parent / "prompts" / f"{message_type}.txt"
    return path.read_text()


def _build_program_details(context: dict) -> str:
    program_type = context.get("program_type", "visit-based")
    if program_type == "visit-based":
        tiers = context.get("tiers", [])
        if tiers:
            lines = ["Reward tiers:"]
            for t in tiers:
                lines.append(f"  - {t['visits']} visits → {t['reward']}")
            return "\n".join(lines)
        return ""
    else:
        wash_packages = context.get("wash_packages", [])
        lines = []
        if wash_packages:
            lines.append("Wash packages (earn pts / redeem cost):")
            for p in wash_packages:
                lines.append(f"  - {p['name']}: earn {p['earn_points']} pt, redeem at {p['redeem_cost']} pts")
        return "\n".join(lines)


def generate_message(message_type: str, context: dict, temperature: float = 0.7, mode: str = "SMS") -> str:
    # Post-redemption flow: customer resets to 0 visits/points.
    # Their next wash triggers the progress message, not welcome.
    # Welcome only fires on initial signup.
    # This function never decides which type to call — the caller (app.py) always
    # passes the correct message_type based on what event is being templated.
    if is_demo_mode():
        from demo_messages import get_demo_message
        # Route welcome to signup-reward pool when a signup reward is configured
        demo_type = message_type
        if message_type == "welcome" and context.get("signup_reward_enabled") and context.get("signup_reward"):
            demo_type = "welcome_with_signup_reward"
        elif message_type == "autoengage" and context.get("ae_type") == "reminder":
            demo_type = "autoengage_reminder"
        message = get_demo_message(demo_type, context, mode=mode)
    else:
        template = _load_prompt(message_type)
        program_details = _build_program_details(context)

        # Build signup reward instruction block for the prompt
        if context.get("signup_reward_enabled") and context.get("signup_reward"):
            signup_reward_block = (
                f"This customer receives a signup reward: {context['signup_reward']}. "
                f"You MUST mention this reward by name. Do NOT mention an expiration window. "
                f"Include the redemption placeholder: ~redeem~"
            )
        else:
            signup_reward_block = ""

        _program_type = context.get("program_type", "visit-based")
        starter_unit = "point" if _program_type == "points-based" else "visit"

        fill = {
            "car_wash_name": context.get("car_wash_name", "our car wash"),
            "program_type": _program_type,
            "program_details": program_details,
            "status_detail": context.get("status_detail", ""),
            "progress_context": context.get("progress_context", ""),
            "reward_description": context.get("reward_description", ""),
            "days_since_visit": context.get("days_since_visit", ""),
            "offer": context.get("offer", ""),
            "package_name": context.get("package_name", ""),
            "redeem_cost": context.get("redeem_cost", ""),
            "signup_reward_block": signup_reward_block,
            "starter_unit": starter_unit,
        }

        prompt = template.format(**fill)

        if mode == "MMS":
            footer_note = (
                " End with the required compliance footer."
                if message_type == "welcome" else
                " Do NOT add a compliance footer."
            )
            prompt += (
                "\n\nIMPORTANT — This is an MMS message. Override the 160-character rule. "
                "Target 400-500 characters total. Write 2-3 short paragraphs separated by blank lines. "
                "Be warmer and more conversational. Include more context and detail." + footer_note
            )

        client = _get_client()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600 if mode == "MMS" else 300,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        message = response.content[0].text.strip()

    # For points-based programs, swap iVision visit tokens for points tokens in
    # Visit Tracked messages. The demo pool uses ~ls~/~lsr~ as source-of-truth;
    # substitution happens here so the pool stays unchanged.
    if message_type == "tracked" and context.get("program_type") == "points-based":
        message = message.replace("~ls~", "~custom3~")
        message = message.replace("~lsr~", "~custom4~")
        message = message.replace("visit(s)", "point(s)")

    return message
