# OptSpot Loyalty Message Generator

**Status: Internal Prototype** — for OptSpot account managers only. Not production-final.

This is an internal tool for OptSpot AMs to configure car wash loyalty programs and generate SMS/MMS message variations. AMs enter program details (car wash name, reward tiers, signup offers) and the app produces ready-to-send message copy for each touchpoint in the loyalty lifecycle: welcome, visit confirmed, progress check, reward unlock, auto-engage win-back, and hot prospect offer. Messages are generated either by the Claude API (live mode) or from a curated template pool (demo mode). Output can be exported as a branded PDF for client review.

## Running locally

1. Clone the repo:
   ```
   git clone <repo-url>
   cd loyalty-generator
   ```

2. Create and activate a virtual environment:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```
   cp .env.example .env
   ```
   To run in demo mode (no API key needed), leave `DEMO_MODE=true` in `.env`.
   To enable live AI generation, add a valid `ANTHROPIC_API_KEY` and set `DEMO_MODE=false`.

5. Set up the app password (required):
   ```
   mkdir -p .streamlit
   ```
   Create `.streamlit/secrets.toml` with:
   ```toml
   app_password = "your-team-password-here"
   ```

6. Run the app:
   ```
   streamlit run app.py
   ```

## Message types

| Type | Trigger |
|---|---|
| Welcome | Loyalty program signup |
| Visit Tracked | After each wash visit |
| Progress Check | Mid-journey nudge toward next reward |
| Reward Unlock | When a reward tier is earned |
| Auto-Engage | Win-back for inactive customers |
| Hot Prospect | Offer for frequent visitors |

## Demo mode vs. live mode

| Mode | When it activates | Message source |
|---|---|---|
| Demo | `DEMO_MODE=true` or no valid API key | Template pool in `demo_messages.py` |
| Live | Valid `ANTHROPIC_API_KEY` and `DEMO_MODE` not `true` | Claude API (claude-sonnet-4-6) |

## Deployment

Deploys to Streamlit Community Cloud. Set `app_password` and `ANTHROPIC_API_KEY` in the Streamlit Cloud secrets manager — never commit `.streamlit/secrets.toml` or `.env` to the repo.
