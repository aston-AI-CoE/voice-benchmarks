# Experiment 05: Real-Time Session Simulation

## Goal

Test whether a realtime voice API can serve as a reliable meeting assistant
over a real 60-minute session — retaining context, answering naturally,
and not hallucinating.

## Why This Design (Validity)

Previous versions had a **validity problem**: we told the model "remember
everything, I'll quiz you later" and planted clean facts at known positions.
That tests context window capacity, not real meeting comprehension.

**This version simulates the real world:**

1. **No priming** — Otto just joins the meeting. No "remember this" instructions.
2. **Messy dialogue** — tangents, interruptions, implicit references, small talk,
   people disagreeing, topic jumping.
3. **Natural questions** — "what was that thing about the color scheme?" not
   "what color scheme did the team decide on for component X?"
4. **Inference required** — "Is Tomas going to be overloaded?" requires connecting
   multiple scattered facts.
5. **Ambiguous questions** — "Who do I talk to about the AWS bill?" tests whether
   Otto can figure out the right answer from context.

## Question Categories

| Category | Count | What it tests |
|----------|-------|---------------|
| action_item | 1 | Can Otto extract action items from messy conversation? |
| decision | 3 | Can Otto identify decisions buried in discussion? |
| detail | 4 | Can Otto recall specific numbers, names, dates? |
| inference | 2 | Can Otto connect dots across different parts of the meeting? |
| ambiguous | 2 | Can Otto handle vague questions and figure out intent? |

## External Transcript Support

You can test with your own real meeting transcripts:

```bash
# Plain text (one line per turn):
# Alice: Hello everyone
# Bob: Hey, how's it going

python3 run_experiment.py --run myrun -e 05 -p openai \
  --transcript /path/to/meeting.txt \
  --questions /path/to/questions.json
```

Questions JSON format:
```json
[
  {
    "question_id": "q1",
    "question": "What did we decide about pricing?",
    "ground_truth": "We decided to raise prices 10% starting Q3",
    "category": "decision",
    "difficulty": "medium",
    "source_minute": 25
  }
]
```

## Pacing

| --seconds-per-minute | Real Duration | Use Case |
|----------------------|---------------|----------|
| 60 | ~60 min | True real-time |
| 30 | ~30 min | Half-speed |
| 5 | ~5 min | Quick functional test |

## Metrics

- **Session survival**: Did the WebSocket last the full meeting?
- **Mid-meeting recall**: Can Otto answer during the meeting?
- **Post-meeting accuracy**: Scored by LLM judge across 5 question categories
- **Hallucination rate**: Does Otto make things up?
- **Latency over time**: Does TTFB degrade as the session grows?
