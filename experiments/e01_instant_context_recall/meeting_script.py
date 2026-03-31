"""Meeting transcript generator with planted facts for context retention testing.

Simulates a 1-hour product meeting between 4 team members.
Facts are planted at specific minutes across 5 categories.
Filler dialogue is realistic meeting chatter to test context retention
under noise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PlantedFact:
    """A specific fact planted at a known point in the meeting."""

    fact_id: str
    minute: int
    category: str  # "name", "number", "decision", "preference", "date"
    statement: str  # The exact text said in the meeting
    ground_truth: str  # Canonical answer for scoring
    difficulty: str = "medium"  # "easy", "medium", "hard"


@dataclass
class MeetingTurn:
    """A single line of meeting dialogue."""

    speaker: str
    minute: int
    text: str
    contains_fact: Optional[str] = None  # fact_id if this turn plants a fact


@dataclass
class MeetingScript:
    """Complete meeting transcript with metadata."""

    title: str
    duration_minutes: int
    speakers: list[str]
    planted_facts: list[PlantedFact]
    turns: list[MeetingTurn]
    version: str = "v1"


# ---------------------------------------------------------------------------
# Planted facts — 20 facts across 5 categories
# ---------------------------------------------------------------------------

PLANTED_FACTS: list[PlantedFact] = [
    # --- Names (4 facts) ---
    PlantedFact(
        fact_id="name_01",
        minute=3,
        category="name",
        statement="By the way, the new hire starting Monday is Priya Raghavan, she's transferring from the Zurich office.",
        ground_truth="The new hire starting Monday is Priya Raghavan from the Zurich office.",
        difficulty="easy",
    ),
    PlantedFact(
        fact_id="name_02",
        minute=28,
        category="name",
        statement="So after evaluating both, we're going with Descope for SSO, not Auth0. Their pricing is much better for our scale.",
        ground_truth="The SSO vendor chosen is Descope, not Auth0.",
        difficulty="medium",
    ),
    PlantedFact(
        fact_id="name_03",
        minute=42,
        category="name",
        statement="The security researcher who found the XSS vulnerability is Marcus Chen. He reported it through our bug bounty program.",
        ground_truth="The security researcher who found the XSS bug is Marcus Chen, via the bug bounty program.",
        difficulty="medium",
    ),
    PlantedFact(
        fact_id="name_04",
        minute=56,
        category="name",
        statement="Our new legal counsel is Jennifer Wu from Morrison and Foerster. She starts next Wednesday.",
        ground_truth="New legal counsel is Jennifer Wu from Morrison & Foerster, starting next Wednesday.",
        difficulty="hard",
    ),
    # --- Numbers (4 facts) ---
    PlantedFact(
        fact_id="number_01",
        minute=7,
        category="number",
        statement="Quick update on financials — the Q2 revenue target has been revised down to four point seven million, from the original five point two million.",
        ground_truth="Q2 revenue target is $4.7 million, revised down from $5.2 million.",
        difficulty="medium",
    ),
    PlantedFact(
        fact_id="number_02",
        minute=33,
        category="number",
        statement="Looking at our burn rate with the new hires factored in, we're at three hundred and eighty thousand per month.",
        ground_truth="Current burn rate is $380K per month including new hires.",
        difficulty="medium",
    ),
    PlantedFact(
        fact_id="number_03",
        minute=45,
        category="number",
        statement="For the enterprise tier, the API rate limit should be set to twelve hundred requests per minute. That's what Stripe and Twilio use as a baseline.",
        ground_truth="Enterprise API rate limit should be 1,200 requests per minute.",
        difficulty="hard",
    ),
    PlantedFact(
        fact_id="number_04",
        minute=58,
        category="number",
        statement="The mobile app crash rate needs to be below zero point three percent before we can go live. That's the App Store threshold for featuring.",
        ground_truth="Mobile app crash rate must drop below 0.3% before launch.",
        difficulty="hard",
    ),
    # --- Decisions (4 facts) ---
    PlantedFact(
        fact_id="decision_01",
        minute=12,
        category="decision",
        statement="Alright, so the decision is final — we're deprecating the v1 REST API by September fifteenth. We'll send the deprecation notice this week.",
        ground_truth="Decision to deprecate v1 REST API by September 15th.",
        difficulty="easy",
    ),
    PlantedFact(
        fact_id="decision_02",
        minute=37,
        category="decision",
        statement="I think we should hold off on the Kubernetes migration until after the SOC 2 audit is complete. No point adding complexity right now.",
        ground_truth="Kubernetes migration postponed until after the SOC 2 audit.",
        difficulty="medium",
    ),
    PlantedFact(
        fact_id="decision_03",
        minute=48,
        category="decision",
        statement="Carol and I talked about this yesterday — we want to switch from Datadog to Grafana Cloud for observability. The cost savings are significant.",
        ground_truth="Switching from Datadog to Grafana Cloud for observability.",
        difficulty="medium",
    ),
    PlantedFact(
        fact_id="decision_04",
        minute=55,
        category="decision",
        statement="We're going to use feature flags for the new checkout flow. LaunchDarkly specifically, since we already have a contract with them.",
        ground_truth="Using LaunchDarkly feature flags for the new checkout flow.",
        difficulty="hard",
    ),
    # --- Preferences (4 facts) ---
    PlantedFact(
        fact_id="preference_01",
        minute=18,
        category="preference",
        statement="I've looked at both prototypes and honestly, I strongly prefer the Figma one over the InVision version. The interactions feel much smoother.",
        ground_truth="Alice prefers the Figma prototype over the InVision version.",
        difficulty="easy",
    ),
    PlantedFact(
        fact_id="preference_02",
        minute=38,
        category="preference",
        statement="For the internal tools, I'd rather we use Retool than build something custom. We don't have the bandwidth for custom admin panels.",
        ground_truth="Bob prefers Retool over building custom internal tools.",
        difficulty="medium",
    ),
    PlantedFact(
        fact_id="preference_03",
        minute=51,
        category="preference",
        statement="The CEO specifically asked that the customer dashboard use a dark theme by default. Apparently their last demo got feedback about the bright white background.",
        ground_truth="CEO wants the customer dashboard to use dark theme by default.",
        difficulty="medium",
    ),
    PlantedFact(
        fact_id="preference_04",
        minute=57,
        category="preference",
        statement="For our coding standards, Carol wants us to adopt the Airbnb style guide for TypeScript instead of the Google one we've been using.",
        ground_truth="Carol wants to adopt Airbnb TypeScript style guide instead of Google's.",
        difficulty="hard",
    ),
    # --- Dates (4 facts) ---
    PlantedFact(
        fact_id="date_01",
        minute=22,
        category="date",
        statement="Heads up, the board meeting got rescheduled. It's now on April twenty-third instead of the thirtieth.",
        ground_truth="Board meeting moved to April 23rd (from April 30th).",
        difficulty="easy",
    ),
    PlantedFact(
        fact_id="date_02",
        minute=40,
        category="date",
        statement="The penetration test is confirmed for the week of May twelfth. The security firm needs us to have staging ready by May ninth.",
        ground_truth="Penetration test scheduled for week of May 12th, staging needed by May 9th.",
        difficulty="medium",
    ),
    PlantedFact(
        fact_id="date_03",
        minute=50,
        category="date",
        statement="Black Friday prep starts October first this year. Marketing wants all performance optimizations done two weeks before that.",
        ground_truth="Black Friday prep starts October 1st, performance optimizations due two weeks before.",
        difficulty="hard",
    ),
    PlantedFact(
        fact_id="date_04",
        minute=59,
        category="date",
        statement="The Series B investor meeting is locked in for June eighteenth. We need the growth metrics deck finalized by June tenth.",
        ground_truth="Series B investor meeting on June 18th, growth deck due June 10th.",
        difficulty="hard",
    ),
]

# ---------------------------------------------------------------------------
# Filler dialogue — realistic meeting conversation between facts
# ---------------------------------------------------------------------------

SPEAKERS = ["Alice", "Bob", "Carol", "David"]


def _filler(minute: int, speaker: str, text: str) -> MeetingTurn:
    return MeetingTurn(speaker=speaker, minute=minute, text=text)


def _fact_turn(fact: PlantedFact, speaker: str) -> MeetingTurn:
    return MeetingTurn(
        speaker=speaker,
        minute=fact.minute,
        text=fact.statement,
        contains_fact=fact.fact_id,
    )


def generate_meeting_script() -> MeetingScript:
    """Generate the full 1-hour meeting script with planted facts and filler."""

    facts_by_minute = {f.minute: f for f in PLANTED_FACTS}
    turns: list[MeetingTurn] = []

    # -- Minutes 0-5: Opening & introductions --
    turns.extend([
        _filler(0, "Alice", "Alright everyone, let's get started. Thanks for joining the weekly product sync."),
        _filler(0, "Bob", "Hey team. I've got a few updates from engineering."),
        _filler(1, "Carol", "Same here, I have some design updates and a couple of blockers to discuss."),
        _filler(1, "David", "Morning. I'll cover the ops side when we get to infrastructure."),
        _filler(2, "Alice", "Great. Let's start with the hiring update since that affects our sprint planning."),
        _filler(2, "Bob", "Sure. We got the offer acceptance yesterday, so we're good to go."),
        _fact_turn(facts_by_minute[3], "Alice"),
        _filler(3, "Bob", "Awesome, Priya has great experience with distributed systems. She'll be a huge help."),
        _filler(4, "Carol", "Should we set up an onboarding buddy for her? I can pair her with someone on my team."),
        _filler(4, "Alice", "That would be great, Carol. Let's make sure she has access to all the repos on day one."),
        _filler(5, "David", "I'll get her cloud accounts provisioned today. AWS, GCP, and the monitoring dashboards."),
    ])

    # -- Minutes 5-10: Financial update --
    turns.extend([
        _filler(5, "Alice", "OK, moving on to the financial update. Bob, you spoke with finance yesterday?"),
        _filler(6, "Bob", "Yeah, so the market conditions have shifted a bit and we need to adjust our targets."),
        _filler(6, "Carol", "Is this because of the enterprise deal that fell through?"),
        _filler(6, "Bob", "Partly that, partly just the macro environment. Let me share the numbers."),
        _fact_turn(facts_by_minute[7], "Bob"),
        _filler(7, "Alice", "That's a notable revision. What's the biggest driver of the shortfall?"),
        _filler(8, "Bob", "Two things — the Acme Corp deal slipped to Q3, and our self-serve conversion rate dipped last month."),
        _filler(8, "David", "Should we be adjusting our infrastructure spend accordingly?"),
        _filler(9, "Bob", "Not yet. The pipeline is still healthy. We just need to close two of the five deals in progress."),
        _filler(9, "Carol", "I can help with the demo materials if that would speed things up."),
        _filler(10, "Alice", "Good idea. Let's circle back on that after the meeting."),
    ])

    # -- Minutes 10-15: API deprecation --
    turns.extend([
        _filler(10, "Alice", "Next topic — the v1 API. We've been talking about this for months. Time to make a call."),
        _filler(11, "Bob", "We still have about forty customers on v1. But the migration guide is ready."),
        _filler(11, "David", "The v1 endpoints are also a maintenance burden. Every deploy we have to test both versions."),
        _fact_turn(facts_by_minute[12], "Alice"),
        _filler(12, "Carol", "September feels right. That gives customers a solid three months to migrate."),
        _filler(13, "Bob", "I'll draft the deprecation email today. We should also put a banner in the docs."),
        _filler(13, "David", "And I'll add sunset headers to v1 responses starting next week."),
        _filler(14, "Alice", "Perfect. Make sure support knows so they can handle any incoming tickets."),
        _filler(14, "Carol", "Should we offer migration office hours? Like a weekly call where customers can get help?"),
        _filler(15, "Alice", "Love that idea. Bob, can you set that up?"),
        _filler(15, "Bob", "On it. I'll use the existing webinar slot on Thursdays."),
    ])

    # -- Minutes 15-20: Design review --
    turns.extend([
        _filler(16, "Alice", "Carol, you mentioned design updates. What have you got?"),
        _filler(16, "Carol", "So I've been working on two prototypes for the new onboarding flow."),
        _filler(17, "Carol", "One's in Figma with the new component library, the other is the existing InVision mockup updated."),
        _filler(17, "Bob", "Which one should we go with? I need to know for sprint planning."),
        _fact_turn(facts_by_minute[18], "Alice"),
        _filler(18, "Carol", "Yeah, the Figma one also uses our new design tokens so it's more future-proof."),
        _filler(19, "David", "Does either prototype account for the mobile responsive breakpoints?"),
        _filler(19, "Carol", "The Figma one does. InVision was desktop only."),
        _filler(20, "Bob", "Another reason to go with Figma. Let's finalize that this week."),
        _filler(20, "Alice", "Agreed. Carol, can you share the Figma link in the design channel?"),
        _filler(21, "Carol", "Already done. I shared it this morning."),
    ])

    # -- Minutes 21-25: Board meeting & scheduling --
    turns.extend([
        _filler(21, "Alice", "One scheduling thing before we move on."),
        _fact_turn(facts_by_minute[22], "Alice"),
        _filler(22, "Bob", "The twenty-third? That's a Wednesday. Do we have the deck ready?"),
        _filler(23, "Alice", "Mostly. We need to update the ARR slide and the product roadmap."),
        _filler(23, "David", "I'll have the infrastructure cost analysis done by Friday for the deck."),
        _filler(24, "Carol", "Should I prepare the design showcase slides too?"),
        _filler(24, "Alice", "Yes please. The board always loves seeing the product evolution visuals."),
        _filler(25, "Bob", "I'll update the engineering velocity metrics. We've actually improved sprint completion by twelve percent."),
        _filler(25, "David", "Nice. Our deploy frequency is also up — we're doing about six deploys a day now."),
    ])

    # -- Minutes 25-30: SSO vendor selection --
    turns.extend([
        _filler(26, "Alice", "OK, let's talk about the SSO integration. David, where are we on that?"),
        _filler(26, "David", "So I've been testing two providers for the last two weeks."),
        _filler(27, "David", "Auth0 has more features but their pricing is aggressive once you pass ten thousand MAUs."),
        _filler(27, "Bob", "And we're already at eight thousand, so we'd hit that ceiling fast."),
        _fact_turn(facts_by_minute[28], "David"),
        _filler(28, "Carol", "I've used Descope before at my last company. Their developer experience is solid."),
        _filler(29, "Alice", "Great. David, can you start the integration this sprint?"),
        _filler(29, "David", "Already started a proof of concept. The SAML flow works, just need to wire up SCIM provisioning."),
        _filler(30, "Bob", "How long do you think the full integration will take?"),
        _filler(30, "David", "Two sprints realistically. One for core SSO, one for SCIM and admin UI."),
    ])

    # -- Minutes 30-35: Burn rate & hiring --
    turns.extend([
        _filler(31, "Alice", "Let me share some context from the finance call I had yesterday about our runway."),
        _filler(31, "Bob", "Yeah, I've been wondering about that with all the new hires."),
        _filler(32, "Alice", "We're in a good position overall, but we need to be mindful."),
        _fact_turn(facts_by_minute[33], "Alice"),
        _filler(33, "David", "Is that sustainable with current funding?"),
        _filler(34, "Alice", "Yes, we have about eighteen months of runway at this rate. But the board wants to see a path to profitability."),
        _filler(34, "Bob", "Makes sense. We should probably hold on any non-critical hires for now."),
        _filler(35, "Carol", "What about the contractor we were going to bring on for the mobile redesign?"),
        _filler(35, "Alice", "Let's evaluate that next month. We might be able to handle it internally."),
    ])

    # -- Minutes 35-40: Infrastructure decisions --
    turns.extend([
        _filler(36, "David", "Speaking of infrastructure, I wanted to bring up the Kubernetes migration."),
        _filler(36, "Bob", "Where are we on that? I thought we were planning for Q3."),
        _fact_turn(facts_by_minute[37], "Bob"),
        _filler(37, "David", "That's fair. The auditors will want to see a stable environment anyway."),
        _filler(38, "Alice", "Agreed. Let's keep it on the roadmap but push the start date to post-audit."),
        _fact_turn(facts_by_minute[38], "Bob"),
        _filler(39, "Carol", "Retool would save us a lot of time. Those admin panels take forever to build from scratch."),
        _filler(39, "David", "I've used Retool too. It handles database queries and API calls out of the box."),
        _fact_turn(facts_by_minute[40], "David"),
        _filler(40, "Alice", "May twelfth. Good, that gives us time to fix anything the auditors flag."),
    ])

    # -- Minutes 40-45: Security update --
    turns.extend([
        _filler(41, "David", "While we're on security, I should mention we had a bug bounty report come in."),
        _filler(41, "Bob", "Serious? What was the severity?"),
        _fact_turn(facts_by_minute[42], "David"),
        _filler(42, "Carol", "An XSS vulnerability? Where was it?"),
        _filler(43, "David", "In the markdown preview component on the settings page. It's already patched."),
        _filler(43, "Bob", "Good catch. How much is the bounty?"),
        _filler(44, "David", "Two thousand dollars. Pretty standard for a medium-severity finding."),
        _filler(44, "Alice", "Let's make sure we do a broader audit of our input sanitization."),
        _fact_turn(facts_by_minute[45], "Bob"),
        _filler(45, "David", "Twelve hundred per minute should be plenty. Our P99 customers are hitting about eight hundred."),
    ])

    # -- Minutes 45-50: Observability & performance --
    turns.extend([
        _filler(46, "Carol", "Can we talk about our monitoring stack? I have some concerns."),
        _filler(46, "David", "Go ahead, I've been thinking about this too."),
        _filler(47, "Carol", "Datadog costs are getting out of hand. We're paying way too much for custom metrics."),
        _filler(47, "David", "Agreed. Last month's bill was almost eight thousand dollars."),
        _fact_turn(facts_by_minute[48], "Carol"),
        _filler(48, "Bob", "Grafana Cloud? I've heard good things but haven't used it in production."),
        _filler(49, "David", "Their hosted Prometheus and Loki stack is really mature now. And it's about sixty percent cheaper."),
        _filler(49, "Alice", "Let's do a proof of concept this sprint. David, can you set up a parallel stack?"),
        _fact_turn(facts_by_minute[50], "Alice"),
        _filler(50, "Bob", "October first feels early. That's only six months away."),
        _filler(50, "Carol", "Marketing always starts early. They learned that lesson last year."),
    ])

    # -- Minutes 50-55: CEO requests & style guide --
    turns.extend([
        _fact_turn(facts_by_minute[51], "Alice"),
        _filler(51, "Carol", "Dark theme by default? I can make that work. We already have the tokens for it."),
        _filler(52, "Bob", "Makes sense from a user perspective too. Most developer tools default to dark mode now."),
        _filler(52, "David", "We'll need to update the email templates too. Those are still hardcoded with light backgrounds."),
        _filler(53, "Alice", "Good catch. Carol, can you own the dark theme migration end to end?"),
        _filler(53, "Carol", "Sure. I'll put together a migration plan this week."),
        _filler(54, "Bob", "Before we wrap up — are we doing anything about our coding standards? I've seen a lot of inconsistency in recent PRs."),
        _fact_turn(facts_by_minute[55], "Carol"),
        _filler(55, "Bob", "LaunchDarkly is solid. We already have the SDK integrated from the last project."),
    ])

    # -- Minutes 55-60: Legal, final items & wrap-up --
    turns.extend([
        _fact_turn(facts_by_minute[56], "Alice"),
        _filler(56, "Bob", "Morrison and Foerster — that's a big firm. Good for the compliance work we need."),
        _filler(57, "David", "Can she help with the GDPR data processing agreement we need to update?"),
        _filler(57, "Alice", "That's exactly why we hired her. GDPR, SOC 2, and the new data residency requirements."),
        _fact_turn(facts_by_minute[57], "Carol"),
        _fact_turn(facts_by_minute[58], "Bob"),
        _filler(58, "Alice", "Absolutely. The App Store team was very clear about that threshold."),
        _fact_turn(facts_by_minute[59], "Alice"),
        _filler(59, "Bob", "June eighteenth for the investor meeting. That's tight but doable."),
        _filler(59, "Carol", "I can have the product demo polished by June fifteenth at the latest."),
        _filler(60, "Alice", "Perfect. Alright everyone, great meeting. Let's execute on everything we discussed. I'll send out a summary."),
        _filler(60, "Bob", "Thanks Alice. Good sync."),
        _filler(60, "Carol", "Thanks all. Talk soon."),
        _filler(60, "David", "Bye everyone."),
    ])

    return MeetingScript(
        title="Weekly Product Sync — Q2 Planning & Operations",
        duration_minutes=60,
        speakers=SPEAKERS,
        planted_facts=PLANTED_FACTS,
        turns=turns,
        version="v1",
    )


def get_fact_categories() -> dict[str, str]:
    """Return fact_id -> category mapping."""
    return {f.fact_id: f.category for f in PLANTED_FACTS}


def get_fact_minutes() -> dict[str, int]:
    """Return fact_id -> minute mapping."""
    return {f.fact_id: f.minute for f in PLANTED_FACTS}
