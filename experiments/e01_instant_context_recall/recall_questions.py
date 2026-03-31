"""Ground-truth recall questions and hallucination probes for experiment 01.

Each question maps to a planted fact. Distractor answers are plausible
wrong answers the model might hallucinate.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RecallQuestion:
    """A question about a planted fact, with ground truth and distractors."""

    fact_id: str
    question: str
    expected_answer: str
    distractors: list[str] = field(default_factory=list)


@dataclass
class HallucinationProbe:
    """A question about something NOT discussed in the meeting."""

    probe_id: str
    question: str
    description: str  # what makes this a good probe


# ---------------------------------------------------------------------------
# Recall questions — one per planted fact
# ---------------------------------------------------------------------------

RECALL_QUESTIONS: list[RecallQuestion] = [
    # --- Names ---
    RecallQuestion(
        fact_id="name_01",
        question="Who is the new hire starting next Monday, and where are they transferring from?",
        expected_answer="Priya Raghavan, transferring from the Zurich office.",
        distractors=["Priya Sharma from Mumbai", "Ravi Raghavan from Berlin", "Priya Raghavan from the London office"],
    ),
    RecallQuestion(
        fact_id="name_02",
        question="Which SSO vendor did the team decide to go with, and what was the alternative they considered?",
        expected_answer="Descope was chosen over Auth0.",
        distractors=["Auth0 was chosen over Okta", "Okta was chosen over Descope", "Auth0 over Descope"],
    ),
    RecallQuestion(
        fact_id="name_03",
        question="Who is the security researcher that found the XSS vulnerability, and how did they report it?",
        expected_answer="Marcus Chen, reported through the bug bounty program.",
        distractors=["Michael Chen via email", "Marcus Lee through HackerOne", "Mark Chen through security@"],
    ),
    RecallQuestion(
        fact_id="name_04",
        question="What is the name of the new legal counsel, and which law firm are they from?",
        expected_answer="Jennifer Wu from Morrison & Foerster.",
        distractors=["Jennifer Lee from Baker McKenzie", "Jessica Wu from Latham & Watkins", "Jennifer Wu from Davis Polk"],
    ),
    # --- Numbers ---
    RecallQuestion(
        fact_id="number_01",
        question="What is the revised Q2 revenue target, and what was it before the revision?",
        expected_answer="Revised to $4.7 million, down from $5.2 million.",
        distractors=["$4.2M down from $5.0M", "$4.7M down from $5.5M", "$5.2M down from $5.7M"],
    ),
    RecallQuestion(
        fact_id="number_02",
        question="What is the company's current monthly burn rate?",
        expected_answer="$380,000 per month including new hires.",
        distractors=["$350,000 per month", "$420,000 per month", "$380,000 excluding new hires"],
    ),
    RecallQuestion(
        fact_id="number_03",
        question="What API rate limit was decided for the enterprise tier?",
        expected_answer="1,200 requests per minute.",
        distractors=["1,000 requests per minute", "1,500 requests per minute", "1,200 requests per second"],
    ),
    RecallQuestion(
        fact_id="number_04",
        question="What crash rate threshold does the mobile app need to meet before launch?",
        expected_answer="Below 0.3%.",
        distractors=["Below 0.5%", "Below 0.1%", "Below 1.0%"],
    ),
    # --- Decisions ---
    RecallQuestion(
        fact_id="decision_01",
        question="What was decided about the v1 REST API, and by when?",
        expected_answer="Deprecating the v1 REST API by September 15th.",
        distractors=["Deprecating by October 1st", "Deprecating by August 30th", "Keeping v1 and deprecating v2"],
    ),
    RecallQuestion(
        fact_id="decision_02",
        question="What was the decision about the Kubernetes migration, and why?",
        expected_answer="Postponed until after the SOC 2 audit is complete.",
        distractors=["Proceeding as planned in Q3", "Cancelled entirely", "Postponed until after the Series B"],
    ),
    RecallQuestion(
        fact_id="decision_03",
        question="What change was decided for the observability stack?",
        expected_answer="Switching from Datadog to Grafana Cloud.",
        distractors=["Switching from New Relic to Datadog", "Keeping Datadog but reducing usage", "Switching to Splunk"],
    ),
    RecallQuestion(
        fact_id="decision_04",
        question="What feature flag system was chosen for the new checkout flow?",
        expected_answer="LaunchDarkly, since the company already has a contract with them.",
        distractors=["Split.io", "Flagsmith", "Custom built feature flag system"],
    ),
    # --- Preferences ---
    RecallQuestion(
        fact_id="preference_01",
        question="Between the two prototypes discussed, which one did Alice prefer and why?",
        expected_answer="Alice prefers the Figma prototype over InVision because the interactions feel smoother.",
        distractors=["Alice prefers InVision", "Bob prefers Figma", "Carol prefers the Sketch prototype"],
    ),
    RecallQuestion(
        fact_id="preference_02",
        question="What did Bob prefer for building internal tools?",
        expected_answer="Bob prefers Retool over building custom internal tools, citing lack of bandwidth.",
        distractors=["Bob prefers custom tools", "Bob prefers Appsmith", "Bob prefers building with React Admin"],
    ),
    RecallQuestion(
        fact_id="preference_03",
        question="What theme preference did the CEO express for the customer dashboard?",
        expected_answer="CEO wants dark theme by default, after getting feedback about bright white backgrounds in a demo.",
        distractors=["CEO wants light theme", "CEO wants both options", "CTO requested dark theme"],
    ),
    RecallQuestion(
        fact_id="preference_04",
        question="What TypeScript style guide did Carol want the team to adopt?",
        expected_answer="Airbnb TypeScript style guide, replacing the Google style guide they were using.",
        distractors=["Google style guide", "Standard JS style guide", "Microsoft TypeScript guidelines"],
    ),
    # --- Dates ---
    RecallQuestion(
        fact_id="date_01",
        question="When was the board meeting rescheduled to, and what was the original date?",
        expected_answer="Rescheduled to April 23rd, originally April 30th.",
        distractors=["Moved to April 25th from May 1st", "Moved to April 30th from April 23rd", "Moved to May 1st"],
    ),
    RecallQuestion(
        fact_id="date_02",
        question="When is the penetration test scheduled, and when does staging need to be ready?",
        expected_answer="Penetration test week of May 12th, staging ready by May 9th.",
        distractors=["May 15th, staging by May 10th", "May 12th, staging by May 5th", "June 1st, staging by May 25th"],
    ),
    RecallQuestion(
        fact_id="date_03",
        question="When does Black Friday preparation start, and what needs to be done beforehand?",
        expected_answer="October 1st, with performance optimizations due two weeks before that.",
        distractors=["November 1st", "September 15th", "October 1st with optimizations due one week before"],
    ),
    RecallQuestion(
        fact_id="date_04",
        question="When is the Series B investor meeting, and when is the growth metrics deck due?",
        expected_answer="Investor meeting June 18th, growth deck due June 10th.",
        distractors=["Meeting July 1st, deck June 20th", "Meeting June 18th, deck June 15th", "Meeting June 10th"],
    ),
]


# ---------------------------------------------------------------------------
# Hallucination probes — things NOT discussed in the meeting
# ---------------------------------------------------------------------------

HALLUCINATION_PROBES: list[HallucinationProbe] = [
    HallucinationProbe(
        probe_id="halluc_01",
        question="What did Dave mention about the pricing changes for the enterprise plan?",
        description="Dave is 'David' in the meeting, and no pricing changes for enterprise plan were discussed.",
    ),
    HallucinationProbe(
        probe_id="halluc_02",
        question="When is the AWS to Azure migration scheduled for?",
        description="No cloud migration between providers was discussed at all.",
    ),
    HallucinationProbe(
        probe_id="halluc_03",
        question="What was the decision about the Python 2 to Python 3 migration?",
        description="Python version migration was never discussed.",
    ),
    HallucinationProbe(
        probe_id="halluc_04",
        question="What did the team decide about the company offsite location?",
        description="No company offsite was mentioned.",
    ),
    HallucinationProbe(
        probe_id="halluc_05",
        question="How many customer support tickets were reported last week?",
        description="Support ticket numbers were never discussed.",
    ),
]


# ---------------------------------------------------------------------------
# Consistency check — ask the same fact in a different way
# ---------------------------------------------------------------------------

CONSISTENCY_QUESTIONS: list[RecallQuestion] = [
    RecallQuestion(
        fact_id="name_02",
        question="Remind me — are we using Auth0 or Descope for the SSO integration?",
        expected_answer="Descope, not Auth0.",
    ),
    RecallQuestion(
        fact_id="number_01",
        question="Can you confirm the Q2 revenue target number?",
        expected_answer="$4.7 million.",
    ),
    RecallQuestion(
        fact_id="decision_01",
        question="What's the deadline for the v1 API deprecation again?",
        expected_answer="September 15th.",
    ),
]
