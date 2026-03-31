"""LLM judge scorer for recall accuracy and hallucination detection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import anthropic

from common.config import get_anthropic_api_key, setup_logging

logger = setup_logging("scoring")


class Verdict(str, Enum):
    CORRECT = "correct"
    PARTIAL = "partial"
    INCORRECT = "incorrect"
    HALLUCINATED = "hallucinated"
    HONEST_UNCERTAINTY = "honest_uncertainty"


@dataclass
class RecallScore:
    """Score for a single recall question."""

    fact_id: str
    verdict: Verdict
    confidence: float  # 0.0–1.0: judge's confidence in the verdict
    partial_credit: float  # 0.0–1.0: how much of the fact was recalled
    hallucinated: bool  # did they fabricate information?
    response_text: str
    expected_text: str
    rationale: str  # judge's reasoning


JUDGE_SYSTEM = """\
You are a precise evaluation judge for a memory recall benchmark. Your job is to \
compare an AI assistant's response against a known ground truth answer and score it.

Respond ONLY with valid JSON matching this schema:
{
  "verdict": "correct" | "partial" | "incorrect" | "hallucinated" | "honest_uncertainty",
  "confidence": 0.0-1.0,
  "partial_credit": 0.0-1.0,
  "hallucinated": true/false,
  "rationale": "brief explanation"
}

Scoring rules:
- CORRECT: Response contains the key factual information from the expected answer. \
Minor wording differences are fine.
- PARTIAL: Response is in the right direction but misses important details \
(e.g. gets the name right but wrong title, or remembers the topic but not the number).
- INCORRECT: Response gives wrong information that doesn't match the expected answer.
- HALLUCINATED: Response confidently states specific information that was NOT in the \
expected answer and is factually wrong. This is worse than INCORRECT because the model \
is fabricating details with confidence.
- HONEST_UNCERTAINTY: Response correctly acknowledges it doesn't remember or isn't sure. \
This is NOT a failure — it's better than hallucinating.

For "partial_credit":
- 1.0 = perfect recall
- 0.5 = got roughly half the key details
- 0.0 = completely wrong or no relevant info

For hallucination probes (expected = "NOT_DISCUSSED"):
- If the model says it wasn't discussed → HONEST_UNCERTAINTY, hallucinated=false
- If the model makes up an answer → HALLUCINATED, hallucinated=true
"""


async def score_recall(
    fact_id: str,
    question: str,
    expected: str,
    actual: str,
    distractors: list[str] | None = None,
) -> RecallScore:
    """Use Claude as an LLM judge to score a single recall response."""

    user_prompt = f"""\
## Recall Question
{question}

## Expected Answer (ground truth)
{expected}

## Model's Actual Response
{actual}
"""
    if distractors:
        user_prompt += f"""
## Known Distractors (plausible wrong answers)
{json.dumps(distractors)}
"""

    client = anthropic.Anthropic(api_key=get_anthropic_api_key())
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fence if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Judge returned invalid JSON: %s", raw)
        data = {
            "verdict": "incorrect",
            "confidence": 0.0,
            "partial_credit": 0.0,
            "hallucinated": False,
            "rationale": f"Judge parse error: {raw[:200]}",
        }

    return RecallScore(
        fact_id=fact_id,
        verdict=Verdict(data.get("verdict", "incorrect")),
        confidence=float(data.get("confidence", 0.0)),
        partial_credit=float(data.get("partial_credit", 0.0)),
        hallucinated=bool(data.get("hallucinated", False)),
        response_text=actual,
        expected_text=expected,
        rationale=data.get("rationale", ""),
    )


@dataclass
class AggregateScores:
    """Aggregated scores across all recall questions."""

    total_questions: int
    recall_accuracy: float  # % correct or partial >= 0.5
    hallucination_rate: float  # % hallucinated
    honest_uncertainty_rate: float  # % honest_uncertainty
    avg_partial_credit: float
    by_category: dict[str, float]  # category -> avg partial_credit
    by_minute: dict[int, float]  # minute -> avg partial_credit


def aggregate_scores(
    scores: list[RecallScore],
    fact_categories: dict[str, str] | None = None,
    fact_minutes: dict[str, int] | None = None,
) -> AggregateScores:
    """Compute aggregate metrics from individual recall scores."""
    if not scores:
        return AggregateScores(0, 0.0, 0.0, 0.0, 0.0, {}, {})

    n = len(scores)
    correct_count = sum(
        1 for s in scores if s.verdict == Verdict.CORRECT or s.partial_credit >= 0.5
    )
    hallucination_count = sum(1 for s in scores if s.hallucinated)
    uncertainty_count = sum(
        1 for s in scores if s.verdict == Verdict.HONEST_UNCERTAINTY
    )
    avg_partial = sum(s.partial_credit for s in scores) / n

    # By category
    by_category: dict[str, list[float]] = {}
    if fact_categories:
        for s in scores:
            cat = fact_categories.get(s.fact_id, "unknown")
            by_category.setdefault(cat, []).append(s.partial_credit)

    # By minute
    by_minute: dict[int, list[float]] = {}
    if fact_minutes:
        for s in scores:
            minute = fact_minutes.get(s.fact_id, -1)
            if minute >= 0:
                by_minute.setdefault(minute, []).append(s.partial_credit)

    return AggregateScores(
        total_questions=n,
        recall_accuracy=correct_count / n,
        hallucination_rate=hallucination_count / n,
        honest_uncertainty_rate=uncertainty_count / n,
        avg_partial_credit=avg_partial,
        by_category={
            k: sum(v) / len(v) for k, v in by_category.items()
        },
        by_minute={
            k: sum(v) / len(v) for k, v in by_minute.items()
        },
    )
