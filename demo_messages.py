"""
Demo message pool — used when DEMO_MODE=true or no valid API key is set.

Each message type has two pools: SMS (≤160 chars) and MMS (400-500 chars).
Regenerate always returns a different variation than the last pick.

Available variables per type:
  All types:    name, reward
  tracked:      status   (e.g. "1 visit logged. 4 more to earn Free Basic Wash.")
  progress:     program_type
  reward:       reward_desc
  autoengage:   days, offer
  hot_prospect: offer

SMS rules:  under 160 chars total; welcome must end with COMPLIANCE_FOOTER
MMS rules:  400-500 chars; 2-3 short paragraphs; welcome still ends with footer
"""

import random

COMPLIANCE_FOOTER = "Stop2Stop Help4Help Msg&DataRatesMayApply"

_last_index: dict[str, int] = {}


def _pick(key: str, variations: list[str]) -> str:
    last = _last_index.get(key, -1)
    choices = [i for i in range(len(variations)) if i != last]
    if not choices:
        choices = list(range(len(variations)))
    idx = random.choice(choices)
    _last_index[key] = idx
    return variations[idx]


def _extract_reward(context: dict) -> str:
    if context.get("program_type") == "points-based":
        return context.get("reward_description") or "a free wash"
    tiers = context.get("tiers", [])
    if tiers:
        return tiers[0].get("reward") or "a free wash"
    return context.get("reward_description") or "a free wash"


def get_demo_message(message_type: str, context: dict, mode: str = "SMS") -> str:
    name = context.get("car_wash_name") or "our car wash"
    reward = _extract_reward(context)
    program_type = context.get("program_type", "visit-based")
    pool_key = f"{message_type}_{mode}"

    # ── WELCOME ───────────────────────────────────────────────────────────────
    if message_type == "welcome":
        f = COMPLIANCE_FOOTER
        starter_unit = "point" if program_type == "points-based" else "visit"

        sms = [
            f"Thanks for joining {name} loyalty! You're already 1 {starter_unit} down toward your first reward. {f}",
            f"Welcome to {name} loyalty! You're already 1 {starter_unit} closer to your reward — keep washing. {f}",
            f"You're in at {name}! 1 {starter_unit} already on your account. Keep washing and your reward will come. {f}",
            f"{name} Rewards: You joined! 1 {starter_unit} already counted. Keep washing — you're on your way. {f}",
        ]

        mms = [
            (
                f"Thanks for joining {name} loyalty!\n\n"
                f"We just got you started — you're already 1 {starter_unit} toward your first reward. "
                f"That was credited automatically the moment you signed up. "
                f"No punchcard, no app, no hassle.\n\n"
                f"Every wash builds your total and you can check your progress anytime here: [TRACK URL]\n\n"
                f"We track everything automatically and will text you when you're close to earning your reward. "
                f"See you next time!"
            ),
            (
                f"Welcome to {name} loyalty!\n\n"
                f"You're already 1 {starter_unit} closer to your reward — we counted it automatically when you joined. "
                f"Every wash after this adds to your total. No card or app needed — just show up and wash.\n\n"
                f"Want to see where you stand anytime? Check your progress here: [TRACK URL]\n\n"
                f"We'll send you a text when you're getting close to earning your reward. "
                f"Thanks for choosing {name}!"
            ),
            (
                f"You're in — welcome to {name} loyalty!\n\n"
                f"Here's where you stand: 1 {starter_unit} is already on your account, credited automatically "
                f"the moment you joined. No action needed on your end — we handle all the tracking for you.\n\n"
                f"Check your loyalty progress here anytime: [TRACK URL]\n\n"
                f"Every wash builds your total and we'll text you when your reward is within reach. "
                f"We're glad you're here. See you soon!"
            ),
            (
                f"{name} loyalty — thanks for joining!\n\n"
                f"Your account is live and you're already 1 {starter_unit} toward your reward. "
                f"That was added automatically when you signed up — no extra steps needed.\n\n"
                f"Every wash after this builds more credit. You can check your progress anytime here: [TRACK URL]\n\n"
                f"We track everything automatically and will send you a message when you've earned your reward. "
                f"Thanks for choosing us."
            ),
        ]

        return _pick(pool_key, mms if mode == "MMS" else sms)

    # ── WELCOME WITH SIGNUP REWARD ────────────────────────────────────────────
    if message_type == "welcome_with_signup_reward":
        f = COMPLIANCE_FOOTER
        sr = context.get("signup_reward", "a free wash")
        starter_unit = "point" if program_type == "points-based" else "visit"

        sms = [
            f"Thanks for joining {name}! Your {sr} is ready: ~redeem~ — you're already 1 {starter_unit} down. {f}",
            f"Welcome to {name}! Your {sr} is ready: ~redeem~ + 1 {starter_unit} already counted. {f}",
            f"You're in at {name}! {sr}: ~redeem~ + 1 {starter_unit} already on your account. {f}",
            f"Joined {name}! {sr}: ~redeem~ — 1 {starter_unit} already on your account. {f}",
        ]

        mms = [
            (
                f"Thanks for joining {name} loyalty!\n\n"
                f"Two things to start you off: your {sr} is ready to claim right now — grab it here: ~redeem~\n\n"
                f"You're also already 1 {starter_unit} toward your next reward. "
                f"That was credited the moment you signed up. "
                f"Every wash after this adds more credit — we track everything, no app needed. "
                f"Check your progress anytime: [TRACK URL]\n\n"
                f"We're glad to have you. {f}"
            ),
            (
                f"Welcome to {name} loyalty!\n\n"
                f"Your {sr} is ready — don't let it sit. Claim it here: ~redeem~\n\n"
                f"You're also already 1 {starter_unit} toward your next reward — we credited it automatically "
                f"the moment you signed up. From here, every wash builds more credit — no card or app needed. "
                f"We'll text you when your next reward is within reach. See your progress: [TRACK URL]\n\n"
                f"See you soon. {f}"
            ),
            (
                f"You're in — welcome to {name} loyalty!\n\n"
                f"Your {sr} is waiting — grab it here: ~redeem~\n\n"
                f"You're also already 1 {starter_unit} toward your next reward. "
                f"We counted it the moment you signed up — no extra steps on your end. "
                f"Every wash after this builds your total automatically. "
                f"Check your progress and see how close you are: [TRACK URL]\n\n"
                f"Thanks for joining. {f}"
            ),
            (
                f"{name} here — thanks for joining!\n\n"
                f"Your {sr} is ready to use whenever you're ready. Claim it here: ~redeem~\n\n"
                f"You're also already 1 {starter_unit} toward your next reward — we put that on your account "
                f"the moment you signed up. Every wash after this builds more credit automatically. "
                f"We track everything and will let you know when your next reward is within reach. "
                f"See progress: [TRACK URL]\n\n"
                f"We're glad to have you. {f}"
            ),
        ]

        return _pick(pool_key, mms if mode == "MMS" else sms)

    # ── TRACKED ───────────────────────────────────────────────────────────────
    elif message_type == "tracked":
        status = context.get("status_detail", "")

        if program_type == "points-based":
            sms = [
                f"{name}: Wash confirmed! Points added to your account. Check balance: [PTS URL]",
                f"Nice work! Points earned at {name}. You're getting closer to {reward}. See total: [PTS URL]",
                f"{name}: Visit logged and points added. Track your progress here: [PTS URL]",
                f"Wash confirmed at {name}! Points are in your account. Balance: [PTS URL]",
            ]
            mms = [
                (
                    f"Wash confirmed at {name}!\n\n"
                    f"Points have been added to your account. "
                    f"Check your current balance here: [PTS URL]\n\n"
                    f"Every wash adds more. Keep coming back and {reward} will be yours before long. "
                    f"We'll let you know when you're close.\n\nThanks for choosing us."
                ),
                (
                    f"{name}: Your visit is on the books.\n\n"
                    f"We added points to your account for today's wash. "
                    f"See your updated total here: [PTS URL]\n\n"
                    f"You're making progress toward {reward}. "
                    f"Stay consistent and you'll get there. We appreciate your business."
                ),
                (
                    f"Visit confirmed at {name}!\n\n"
                    f"Points earned and added to your account. "
                    f"Every wash gets you closer to {reward}.\n\n"
                    f"Track your balance anytime here: [PTS URL] — "
                    f"we'll also text you when you're close to redeeming. See you next time."
                ),
                (
                    f"Got your wash at {name}!\n\n"
                    f"Points have been credited to your loyalty account. "
                    f"View your current balance: [PTS URL]\n\n"
                    f"Keep the momentum going — {reward} is within reach. "
                    f"We'll send you a heads-up when you're almost there."
                ),
            ]
        else:
            sms = [
                f"Wash tracked at {name}! {status}",
                f"{name}: Got your wash. {status}",
                f"Visit confirmed at {name}. {status}",
                f"{name} logged your wash. {status}",
            ]
            mms = [
                (
                    f"Wash confirmed at {name}!\n\n"
                    f"{status}\n\n"
                    f"Every visit adds up. Keep coming back and your reward will be waiting "
                    f"before you know it. We track everything — nothing falls through the cracks.\n\n"
                    f"See you next time!"
                ),
                (
                    f"{name}: Visit logged!\n\n"
                    f"{status}\n\n"
                    f"You're making great progress. Stay consistent and "
                    f"your reward will come sooner than you think. "
                    f"We'll send you a reminder when you're getting close.\n\nThanks for coming in."
                ),
                (
                    f"Got it — another wash on the books at {name}.\n\n"
                    f"{status}\n\n"
                    f"You're on your way. We keep track automatically so you never lose progress. "
                    f"We'll notify you when you hit your goal. Keep it up!"
                ),
                (
                    f"Visit confirmed at {name}!\n\n"
                    f"{status}\n\n"
                    f"You're building momentum. A few more visits and your reward is yours. "
                    f"Thanks for choosing us — we appreciate your loyalty."
                ),
            ]

        return _pick(pool_key, mms if mode == "MMS" else sms)

    # ── PROGRESS ──────────────────────────────────────────────────────────────
    elif message_type == "progress":
        f = COMPLIANCE_FOOTER

        sms = [
            f"Great to see you again at {name}! Track your loyalty visits here: [TRACK URL] {f}",
            f"Thanks for stopping by {name}! Check your progress anytime: [TRACK URL] {f}",
            f"Visit logged at {name}! See your loyalty progress: [TRACK URL] {f}",
            f"{name}: Great to have you back! Follow your progress here: [TRACK URL] {f}",
        ]

        mms = [
            (
                f"Great to see you again at {name}!\n\n"
                f"Every wash you take is tracked automatically as part of your loyalty program. "
                f"You don't need an app or a card — we handle all of it for you. "
                f"Click the link below to see your current progress and how close you are to your next reward: [TRACK URL]\n\n"
                f"Keep coming in and the credits will add up. "
                f"We'll send you a message when you've earned your reward so you know exactly when to claim it. "
                f"See you next time!"
            ),
            (
                f"Thanks for stopping by {name}!\n\n"
                f"Your loyalty progress is tracked automatically — every visit counts and nothing slips through. "
                f"To see exactly where you stand right now and how many more visits you need to earn your reward, "
                f"just click here: [TRACK URL]\n\n"
                f"Stay consistent and you'll get there. "
                f"We'll also send you a text when you're close to your goal and again when your reward is ready to claim. "
                f"Thanks for your loyalty."
            ),
            (
                f"Visit confirmed at {name}!\n\n"
                f"We log every wash automatically so you never have to wonder where you stand. "
                f"Your loyalty progress is always just a click away — see your current total "
                f"and how close you are to your next reward here: [TRACK URL]\n\n"
                f"Keep the visits coming and we'll take care of the rest. "
                f"You'll get a text from us when your reward is ready. "
                f"We appreciate your business — see you soon."
            ),
            (
                f"{name}: Great to have you back!\n\n"
                f"Your loyalty visits are tracked automatically with every wash — "
                f"no cards, no apps, no hassle. "
                f"Want to see where you stand? Your progress is always available here: [TRACK URL]\n\n"
                f"Every visit counts toward your reward, and we track all of it for you. "
                f"We'll also let you know when you're getting close and when your reward is ready to claim. "
                f"Come back soon!"
            ),
        ]

        return _pick(pool_key, mms if mode == "MMS" else sms)

    # ── REWARD ────────────────────────────────────────────────────────────────
    elif message_type == "reward":
        reward_desc = context.get("reward_description") or reward

        sms = [
            f"You earned it! Your {reward_desc} is ready at {name}. Redeem here: ~redeem~",
            f"{name}: {reward_desc} unlocked! Come in and claim it: ~redeem~",
            f"Great news from {name} — you've earned a {reward_desc}. Use it here: ~redeem~",
            f"You hit your goal at {name}! Your {reward_desc} is waiting: ~redeem~",
        ]

        mms = [
            (
                f"Congratulations — you earned it!\n\n"
                f"Your {reward_desc} is ready and waiting at {name}. "
                f"This is your reward for being a loyal customer, and you earned every bit of it.\n\n"
                f"Redeem it here: ~redeem~\n\n"
                f"Come in anytime — your reward will be on file. Thanks for choosing us."
            ),
            (
                f"{name}: Your reward is ready!\n\n"
                f"You've reached your goal and earned a {reward_desc}. "
                f"We're glad you kept coming back — your loyalty means a lot to us.\n\n"
                f"Claim it here: ~redeem~\n\n"
                f"No rush — come in when you're ready and we'll take care of the rest."
            ),
            (
                f"Big news from {name}!\n\n"
                f"You've earned a {reward_desc}. You put in the visits "
                f"and now it's time to enjoy the reward.\n\n"
                f"Redeem here: ~redeem~\n\n"
                f"Your reward doesn't expire right away — come in when it works for you. "
                f"Thank you for your loyalty."
            ),
            (
                f"Well done — your {reward_desc} is ready at {name}.\n\n"
                f"You earned this through consistent visits. "
                f"It's our way of saying thank you for choosing us again and again.\n\n"
                f"Use your reward here: ~redeem~\n\n"
                f"We hope to see you soon. Thanks for being part of the {name} loyalty program."
            ),
        ]

        return _pick(pool_key, mms if mode == "MMS" else sms)

    # ── AUTO-ENGAGE ───────────────────────────────────────────────────────────
    elif message_type == "autoengage":
        days = context.get("days_since_visit", "a while")
        offer = context.get("offer") or "a special offer"

        sms = [
            f"It's been {days} days since your last wash at {name}. Come back and get {offer}: ~redeem~",
            f"Miss you at {name}! Here's {offer} to welcome you back: ~redeem~",
            f"{name} wants you back. It's been {days} days — grab {offer} on your next visit: ~redeem~",
            f"Haven't seen you in {days} days! Come back to {name} and enjoy {offer}: ~redeem~",
        ]

        mms = [
            (
                f"Hey — it's been {days} days since your last visit at {name}.\n\n"
                f"We've been thinking about you. To welcome you back, "
                f"we'd like to offer you: {offer}.\n\n"
                f"No strings attached — just our way of saying we appreciate your business "
                f"and we'd love to see you again. Claim it here: ~redeem~"
            ),
            (
                f"{name} misses you!\n\n"
                f"It's been {days} days and we want to make it worth your while to come back. "
                f"Here's what we have for you: {offer}.\n\n"
                f"All you have to do is show up — we'll handle the rest. "
                f"Redeem here: ~redeem~\n\nWe hope to see you soon."
            ),
            (
                f"It's been a while since we've seen you at {name} — {days} days to be exact.\n\n"
                f"We want to welcome you back with something special: {offer}. "
                f"Think of it as our way of saying we value your business.\n\n"
                f"Use your offer here: ~redeem~\n\n"
                f"Come in anytime. The team would love to see you again."
            ),
            (
                f"A lot can change in {days} days — but your welcome at {name} hasn't.\n\n"
                f"We're offering you {offer} to get back in the groove. "
                f"No catch, no fine print. Just a genuine thank-you for being a customer.\n\n"
                f"Claim it here: ~redeem~\n\nSee you soon!"
            ),
        ]

        return _pick(pool_key, mms if mode == "MMS" else sms)

    # ── AUTO-ENGAGE REMINDER ──────────────────────────────────────────────────
    if message_type == "autoengage_reminder":
        days = context.get("days_since_visit", "a while")

        sms = [
            f"Hey from {name} — it's been a minute! Stop by anytime, we'd love to see you. Stop2Stop Help4Help",
            f"Miss you at {name}! No catch, just a hello. Swing by when you're ready. Stop2Stop Help4Help",
            f"Quick check-in from {name} — hope all's well. Your wash is waiting whenever you are. Stop2Stop Help4Help",
            f"Hi from the {name} team! Just wanted to say hi. Come see us soon. Stop2Stop Help4Help",
        ]

        mms = [
            (
                f"Hey — just checking in from {name}.\n\n"
                f"It's been {days} days since your last visit and we wanted to say hi. "
                f"No offer, no strings — we just appreciate your business and wanted to reach out.\n\n"
                f"Come see us whenever you're ready. We'll be here."
            ),
            (
                f"We miss you at {name}!\n\n"
                f"It's been a while — {days} days, to be exact. "
                f"We hope everything is going well on your end.\n\n"
                f"Your car's always welcome here. "
                f"Stop by anytime and we'll take great care of it. See you soon!"
            ),
            (
                f"A quick hello from {name}.\n\n"
                f"We noticed it's been {days} days since your last wash and just wanted to check in. "
                f"No pressure, no pitch — just a genuine note from our team.\n\n"
                f"We value your business and we'd love to see you again when the time is right."
            ),
            (
                f"Hi from the {name} team!\n\n"
                f"We haven't seen you in {days} days and we wanted to pop in. "
                f"We hope all is well.\n\n"
                f"Your loyalty means a lot to us. Come back anytime — "
                f"we'll be ready to give your car the wash it deserves."
            ),
        ]

        return _pick(pool_key, mms if mode == "MMS" else sms)

    # ── HOT PROSPECT ──────────────────────────────────────────────────────────
    elif message_type == "hot_prospect":
        offer = context.get("offer") or "a special thank-you offer"

        sms = [
            f"Thanks for being a regular at {name}! Here's a thank-you: {offer} ~redeem~",
            f"You've been coming in a lot — we appreciate it. Enjoy {offer} at {name}: ~redeem~",
            f"{name} noticed you've been a loyal customer. Here's something just for you: {offer} ~redeem~",
            f"You're one of our best customers at {name}. Enjoy {offer} on us: ~redeem~",
        ]

        mms = [
            (
                f"We see you've been coming in regularly at {name} — and we want to say thank you.\n\n"
                f"Because you've been such a loyal customer, we have something special for you: {offer}.\n\n"
                f"This is our way of recognizing customers who keep showing up. You've earned it. "
                f"Redeem here: ~redeem~\n\nThank you. It means more than you know."
            ),
            (
                f"{name} has noticed you're one of our most loyal customers.\n\n"
                f"That means something to us. To show our appreciation, "
                f"we'd like to give you: {offer}.\n\n"
                f"No hoops to jump through — just come in and claim it. "
                f"Use it here: ~redeem~\n\nThank you for choosing {name} again and again."
            ),
            (
                f"You've been coming in a lot and we haven't said thank you properly.\n\n"
                f"Consider this your VIP moment at {name}. "
                f"We're giving you {offer} — just because you've been outstanding.\n\n"
                f"Come in and claim it anytime: ~redeem~\n\n"
                f"We're lucky to have customers like you. Thank you for your loyalty."
            ),
            (
                f"Not everyone gets this message — you've earned it.\n\n"
                f"Because of your consistent visits to {name}, "
                f"we're offering you something special: {offer}.\n\n"
                f"It's our thank-you for being exactly the kind of customer we love. "
                f"Redeem here: ~redeem~\n\nSee you next time at {name}."
            ),
        ]

        return _pick(pool_key, mms if mode == "MMS" else sms)

    return f"[Demo] No variations found for '{message_type}'. Add them in demo_messages.py."
