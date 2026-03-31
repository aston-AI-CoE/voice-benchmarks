"""Generates filler conversation and unique facts for stress testing."""

from __future__ import annotations

import random
from dataclasses import dataclass

# Realistic meeting topics for filler
FILLER_TOPICS = [
    "Let me give you a quick update on the sprint velocity. We completed fourteen story points last week.",
    "The design review for the checkout page is scheduled for tomorrow afternoon.",
    "I noticed the CI pipeline is taking about twelve minutes now. We should look into parallelizing the test suite.",
    "Customer support reported a spike in tickets about the export feature. Mostly confusion about the CSV format.",
    "The marketing team wants us to add UTM parameter tracking to all outbound links.",
    "We got feedback from the beta group that the search feature is too slow on mobile devices.",
    "The documentation needs an update for the new webhook endpoints we shipped last week.",
    "I'm thinking we should add a feature tour for first-time users. The activation rate is below target.",
    "The database migration went smoothly last night. Zero downtime, all tables updated.",
    "We need to renew the SSL certificates for the staging environment by next Friday.",
    "The accessibility audit flagged twelve issues. Most are contrast ratio problems in the sidebar.",
    "Engineering is at ninety percent capacity this sprint. We should be careful about scope creep.",
    "The A/B test on the pricing page is showing a seven percent improvement in conversion.",
    "Someone should look into the memory leak in the notification service. It's consuming more RAM each day.",
    "The partner API integration with Stripe is almost done. Just need to handle the webhook verification.",
    "We got approval to upgrade to the latest version of React. That should fix the hydration warnings.",
    "The user research sessions last week revealed that people want better filtering in the dashboard.",
    "Our CDN costs went up fifteen percent this month. Mostly due to the new video feature.",
    "The QA team found a regression in the password reset flow. It's not sending the email in some cases.",
    "We should schedule a tech debt sprint soon. The backlog is getting unwieldy.",
    "The product analytics show that seventy percent of users never click on the notifications bell.",
    "I finished the competitive analysis. Our main differentiator is still the real-time collaboration feature.",
    "The legal team approved the updated terms of service. We can deploy them next Monday.",
    "We're seeing higher than expected latency on the search endpoint during peak hours.",
    "The onboarding funnel has a thirty-two percent drop-off at the email verification step.",
    "Infrastructure costs are tracking to budget this quarter. The reserved instances helped a lot.",
    "The mobile app crash reports have decreased by forty percent since the last release.",
    "We need to update our dependency on the maps library. There's a known vulnerability in the current version.",
    "The customer success team is asking for a bulk import feature for enterprise accounts.",
    "Performance testing showed the API can handle about two thousand concurrent connections.",
]


@dataclass
class AnchorFact:
    """The anchor fact planted at the start of the conversation."""
    codename: str
    budget: str
    location: str


def generate_filler_block(target_tokens: int) -> list[str]:
    """Generate filler conversation turns to reach approximate token count.

    Roughly 1.3 tokens per word. Each filler line is ~15-25 words (~20-33 tokens).
    """
    turns = []
    estimated_tokens = 0
    speakers = ["Alice", "Bob", "Carol", "David"]

    while estimated_tokens < target_tokens:
        topic = random.choice(FILLER_TOPICS)
        speaker = random.choice(speakers)
        text = f"[{speaker}]: {topic}"
        turns.append(text)
        estimated_tokens += int(len(topic.split()) * 1.3)

    return turns


# Unique facts to plant at milestones
_MILESTONE_FACTS = [
    {
        "statement": "The new office pet's name is Biscuit, a golden retriever.",
        "question": "What's the name of the office pet?",
        "key_term": "Biscuit",
    },
    {
        "statement": "The company's wifi password was changed to 'NorthStar2026!'.",
        "question": "What was the company wifi password changed to?",
        "key_term": "NorthStar2026",
    },
    {
        "statement": "The employee appreciation event is at the Rosewood Hotel.",
        "question": "Where is the employee appreciation event?",
        "key_term": "Rosewood",
    },
    {
        "statement": "The emergency contact for the server room is extension 4471.",
        "question": "What's the emergency contact extension for the server room?",
        "key_term": "4471",
    },
    {
        "statement": "The new conference room on the fifth floor is named 'Aurora'.",
        "question": "What's the name of the new conference room on the fifth floor?",
        "key_term": "Aurora",
    },
    {
        "statement": "The quarterly all-hands meeting code is 'Horizon-Delta'.",
        "question": "What's the code for the quarterly all-hands meeting?",
        "key_term": "Horizon-Delta",
    },
    {
        "statement": "The backup server IP address is 10.42.88.17.",
        "question": "What's the backup server IP address?",
        "key_term": "10.42.88.17",
    },
]


def generate_unique_fact(milestone: int) -> dict:
    """Return a unique fact for the given milestone."""
    idx = MILESTONES_ORDER.get(milestone, 0) % len(_MILESTONE_FACTS)
    return _MILESTONE_FACTS[idx]


# Map milestones to fact indices
MILESTONES_ORDER = {
    100: 0,
    500: 1,
    1_000: 2,
    2_000: 3,
    5_000: 4,
    10_000: 5,
    20_000: 6,
}
