#!/usr/bin/env python3
"""
test_preamble.py — capture alpha preamble (commentary) audio for listening

Sends questions to gpt-realtime-alpha-dolphin-6, captures commentary and
final_answer audio separately per phase, saves as WAV files.

Usage:
    python3 scripts/test_preamble.py                     # high effort, 3 questions
    python3 scripts/test_preamble.py --effort medium
    python3 scripts/test_preamble.py --output-dir /tmp/preambles

Output: one WAV per question per phase, e.g.:
    q01_commentary.wav   ← the preamble — "let me check the transcript..."
    q01_final_answer.wav ← the actual answer
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import wave

import websockets

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.config import get_openai_api_key

REALTIME_URL = "wss://api.openai.com/v1/realtime"
MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-alpha-dolphin-6")
SAMPLE_RATE = 24000

# Meeting transcript injected as context — complex enough to trigger reasoning
MEETING_CONTEXT = """\
=== MEETING TRANSCRIPT ===
[Sarah Chen]: Let's start with the Meridian integration. We need to decide on the timeline.
[James Park]: I've reviewed the spec. The API compatibility issues are more complex than expected. We need at least 6 weeks, not 4.
[Sarah Chen]: That pushes the Q3 deadline. What if we parallelize the auth layer and the data migration?
[James Park]: Auth layer is a hard dependency — data migration can't start until SSO is validated. Can't parallelize those two.
[Alice Russo]: The Gong integration is blocked on the same auth layer. If Meridian slips, Gong slips too.
[Sarah Chen]: Okay. 6 weeks for Meridian. Alice, status on the webhook rate limiting?
[Alice Russo]: The webhook is live in staging. We hit rate limiting at 200 concurrent requests — fix is in review, should merge by Friday.
[James Park]: I'll verify the concurrency cap once it merges.
[Sarah Chen]: Last item — the Q3 customer demo. We need Meridian search working end-to-end for it. James, can we carve out a demo environment separate from the staging deploy?
[James Park]: Yes, I can set up a read-only demo env. It won't have live data but will show the full flow.
[Sarah Chen]: Perfect. Let's target end of week 5 for that demo build. Any blockers?
[James Park]: Only the auth dependency. If SSO slips, the demo slips.
=== END TRANSCRIPT ==="""

# Questions designed to require reasoning → should trigger preambles
QUESTIONS = [
    "Hey Otto, what did James say about the Meridian timeline and why can't we parallelize the work?",
    "Hey Otto, what's the chain of dependencies blocking the Q3 demo? Walk me through them.",
    "Hey Otto, if the SSO validation slips by 2 weeks, what else gets delayed and by how much?",
]

_IGNORABLE = {
    "input_audio_buffer_commit_empty",
    "input_audio_buffer_committed",
    "conversation_already_has_active_response",
    "response_not_found",
    "response_cancel_inactive",
    "response_cancel_not_active",
}


def _save_wav(path: str, pcm_chunks: list[bytes]) -> float:
    pcm = b"".join(pcm_chunks)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return len(pcm) / (SAMPLE_RATE * 2)


async def run(effort: str, output_dir: str) -> None:
    api_key = get_openai_api_key()
    os.makedirs(output_dir, exist_ok=True)

    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{REALTIME_URL}?model={MODEL}"

    print(f"Connecting — model={MODEL}  effort={effort}")

    async with websockets.connect(url, additional_headers=headers) as ws:
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": MODEL,
                "instructions": (
                    "You are Otto, an AI meeting assistant. "
                    "Before giving your answer, speak a brief out-loud preamble — "
                    "for example: 'Let me check the transcript for that.' or "
                    "'One moment, looking that up.' — then deliver your answer.\n\n"
                    + MEETING_CONTEXT
                ),
                "output_modalities": ["audio"],
                "audio": {
                    "output": {
                        "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                        "voice": "alloy",
                    },
                },
                "reasoning": {"effort": effort},
                "turn_detection": {"type": "none"},
            },
        }))

        # Wait for session confirmed, handle alpha-specific rejections
        while True:
            event = json.loads(await ws.recv())
            et = event.get("type", "")
            if et == "session.updated":
                vad = event.get("session", {}).get("turn_detection")
                print(f"Session ready (VAD={'active' if vad else 'off'})")
                break
            if et == "error":
                code = event.get("error", {}).get("code", "")
                if code == "unknown_parameter":
                    continue  # alpha silently applies known params, retries not needed
                print(f"Session error: {event['error']['message']}")
                return

        for i, question in enumerate(QUESTIONS):
            label = f"q{i+1:02d}"
            print(f"\n{'─'*60}")
            print(f"Q{i+1}: {question}")

            await ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": question}],
                },
            }))
            await ws.send(json.dumps({"type": "response.create"}))

            item_phases: dict[str, str] = {}
            audio_chunks: dict[str, list[bytes]] = {}
            text: dict[str, str] = {"commentary": "", "final_answer": ""}

            while True:
                event = json.loads(await ws.recv())
                et = event.get("type", "")

                if et == "response.output_item.added":
                    item = event.get("item", {})
                    item_id = item.get("id", "")
                    phase = item.get("phase", "final_answer")
                    item_phases[item_id] = phase
                    audio_chunks.setdefault(phase, [])
                    if phase == "commentary":
                        print("  [preamble started]")

                elif et == "response.audio.delta":
                    item_id = event.get("item_id", "")
                    phase = item_phases.get(item_id, "final_answer")
                    audio_chunks.setdefault(phase, []).append(
                        base64.b64decode(event.get("delta", ""))
                    )

                elif et in ("response.text.delta", "response.audio_transcript.delta",
                            "response.output_audio_transcript.delta"):
                    item_id = event.get("item_id", "")
                    phase = item_phases.get(item_id, "final_answer")
                    text[phase] = text.get(phase, "") + event.get("delta", "")

                elif et == "response.done":
                    break

                elif et == "error":
                    code = event.get("error", {}).get("code", "")
                    if code not in _IGNORABLE:
                        print(f"  Error: {event['error']['message']}")
                    break

            # Save WAV files
            saved = []
            for phase in ("commentary", "final_answer"):
                chunks = audio_chunks.get(phase, [])
                if not chunks:
                    continue
                path = os.path.join(output_dir, f"{label}_{phase}.wav")
                dur = _save_wav(path, chunks)
                saved.append((phase, path, dur))
                print(f"  [{phase}] {dur:.1f}s → {path}")

            if text.get("commentary"):
                print(f"  Preamble text : {text['commentary']!r}")
            if text.get("final_answer"):
                print(f"  Answer text   : {text['final_answer'][:120]}")

            if not audio_chunks.get("commentary"):
                print("  WARNING: no preamble audio captured — try --effort high")

    print(f"\nDone. Files in: {output_dir}")
    print("Play: aplay <file>.wav  (Linux)  |  afplay <file>.wav  (macOS)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture alpha preamble audio")
    parser.add_argument("--effort", default="high",
                        choices=["minimal", "low", "medium", "high"])
    parser.add_argument("--output-dir", default="/tmp/preamble_test")
    args = parser.parse_args()
    asyncio.run(run(args.effort, args.output_dir))
