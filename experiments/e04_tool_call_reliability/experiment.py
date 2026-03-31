"""Experiment 04: Tool Call Reliability.

Tests whether the model correctly invokes (or avoids invoking) tools
based on user prompts, and whether arguments are well-formed.
"""

from __future__ import annotations

import json

from common.config import setup_logging
from common.provider import RealtimeProvider

logger = setup_logging("experiment.04")

ASSISTANT_PROMPT = """\
You are Otto, an AI assistant with access to tools. Use the lookup_data tool \
when the user asks you to search, look up, or query information from the database. \
Do NOT use the tool for general knowledge questions you can answer directly. \
Keep responses concise.\
"""

BENCHMARK_TOOLS = [
    {
        "type": "function",
        "name": "lookup_data",
        "description": "Search the company database for information. Use this when the user asks to look up, search, or query specific company data like sales numbers, customer records, or inventory.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to run against the database",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 10)",
                },
                "category": {
                    "type": "string",
                    "enum": ["sales", "customers", "inventory", "employees", "general"],
                    "description": "The data category to search in",
                },
            },
            "required": ["query"],
        },
    }
]

# Prompts that SHOULD trigger a tool call
SHOULD_CALL = [
    ("Look up the latest sales numbers for Q2.", "sales"),
    ("Search the database for customer complaints about shipping.", "customers"),
    ("Can you query the inventory for items with less than 10 units in stock?", "inventory"),
    ("Pull up the employee records for the engineering department.", "employees"),
    ("Search for all orders placed in the last 24 hours.", "sales"),
    ("Look up how many active enterprise customers we have.", "customers"),
    ("Query the database for products that are out of stock.", "inventory"),
    ("Find all employees who started this quarter.", "employees"),
]

# Prompts that should NOT trigger a tool call
SHOULD_NOT_CALL = [
    "What is the capital of France?",
    "Explain what a database index is.",
    "Tell me a joke about programming.",
    "What does SQL stand for?",
    "How does a hash table work?",
    "What's the difference between REST and GraphQL?",
    "Summarize the benefits of microservices.",
    "What year was Python first released?",
]


async def run(
    provider: RealtimeProvider,
    *,
    dry_run: bool = False,
    skip_scoring: bool = False,
) -> dict:
    """Run tool call reliability test."""
    if dry_run:
        return {
            "experiment": "e04_tool_call_reliability",
            "dry_run": True,
            "should_call_prompts": len(SHOULD_CALL),
            "should_not_call_prompts": len(SHOULD_NOT_CALL),
        }

    logger.info(
        "Starting experiment 04 (tool reliability) with %s",
        provider.name,
    )

    await provider.connect(
        instructions=ASSISTANT_PROMPT,
        tools=BENCHMARK_TOOLS,
    )

    # Test prompts that SHOULD trigger tool calls
    true_positives = 0
    false_negatives = 0
    should_call_results = []

    for prompt, expected_category in SHOULD_CALL:
        turn = await provider.send_text(prompt)
        called = len(turn.tool_calls) > 0
        correct_tool = any(tc["name"] == "lookup_data" for tc in turn.tool_calls) if called else False

        # Check argument quality
        arg_quality = None
        if turn.tool_calls:
            try:
                args = json.loads(turn.tool_calls[0].get("arguments", "{}"))
                has_query = bool(args.get("query"))
                correct_category = args.get("category") == expected_category
                arg_quality = {
                    "has_query": has_query,
                    "query_value": args.get("query"),
                    "category": args.get("category"),
                    "correct_category": correct_category,
                }
            except json.JSONDecodeError:
                arg_quality = {"parse_error": True}

        if called and correct_tool:
            true_positives += 1
            # Send mock result so model can continue
            for tc in turn.tool_calls:
                await provider.handle_tool_call(
                    tc["call_id"],
                    json.dumps({"results": [{"note": "Mock benchmark result"}], "count": 1}),
                )
        else:
            false_negatives += 1

        should_call_results.append({
            "prompt": prompt,
            "expected_category": expected_category,
            "tool_called": called,
            "correct_tool": correct_tool,
            "arg_quality": arg_quality,
            "response": turn.text[:200],
        })
        logger.info("  SHOULD_CALL: %s → called=%s", prompt[:40], called)

    # Test prompts that should NOT trigger tool calls
    true_negatives = 0
    false_positives = 0
    should_not_call_results = []

    for prompt in SHOULD_NOT_CALL:
        turn = await provider.send_text(prompt)
        called = len(turn.tool_calls) > 0

        if not called:
            true_negatives += 1
        else:
            false_positives += 1
            # Still handle the tool call to avoid breaking the session
            for tc in turn.tool_calls:
                await provider.handle_tool_call(
                    tc["call_id"],
                    json.dumps({"results": [], "count": 0}),
                )

        should_not_call_results.append({
            "prompt": prompt,
            "tool_called": called,
            "response": turn.text[:200],
        })
        logger.info("  SHOULD_NOT_CALL: %s → called=%s", prompt[:40], called)

    metrics = await provider.get_session_metrics()
    await provider.disconnect()

    total = len(SHOULD_CALL) + len(SHOULD_NOT_CALL)
    accuracy = (true_positives + true_negatives) / total if total else 0
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    logger.info(
        "=== RESULTS: accuracy=%.0f%% precision=%.0f%% recall=%.0f%% f1=%.2f ===",
        accuracy * 100, precision * 100, recall * 100, f1,
    )

    return {
        "experiment": "e04_tool_call_reliability",
        "provider": provider.name,
        "config": {
            "tool_name": "lookup_data",
            "should_call_count": len(SHOULD_CALL),
            "should_not_call_count": len(SHOULD_NOT_CALL),
        },
        "should_call_results": should_call_results,
        "should_not_call_results": should_not_call_results,
        "aggregate": {
            "true_positives": true_positives,
            "false_negatives": false_negatives,
            "true_negatives": true_negatives,
            "false_positives": false_positives,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
        },
        "session_metrics": {
            "total_input_tokens": metrics.total_input_tokens,
            "total_output_tokens": metrics.total_output_tokens,
            "errors": metrics.errors,
            "connection_drops": metrics.connection_drops,
        },
    }
