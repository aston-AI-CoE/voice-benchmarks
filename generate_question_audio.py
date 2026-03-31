#!/usr/bin/env python3
"""Generate TTS audio for mid-meeting and post-meeting questions.

These are the "Hey Otto" questions that get asked during/after the meeting.
Stored in audio_fixtures/meeting_1hr_questions/

Usage:
    python3 generate_question_audio.py
    python3 generate_question_audio.py --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common.audio import AUDIO_FIXTURES_DIR, SAMPLE_RATE, SAMPLE_WIDTH
from common.config import setup_logging

logger = setup_logging("generate_question_audio")

# Questions are asked by Alice (the meeting lead)
QUESTION_VOICE = "nova"


async def generate_tts(text: str, voice: str) -> bytes:
    import httpx
    from common.config import get_openai_api_key

    api_key = get_openai_api_key()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "tts-1-hd",
                "input": text,
                "voice": voice,
                "response_format": "pcm",
                "speed": 1.0,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.content


async def main():
    parser = argparse.ArgumentParser(description="Generate question audio")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    from experiments.e05_realtime_session_1hr.meeting_1hr import generate_meeting_1hr
    meeting = generate_meeting_1hr()

    fixture_dir = AUDIO_FIXTURES_DIR / "meeting_1hr_questions"
    manifest_path = fixture_dir / "manifest.json"

    if manifest_path.exists() and not args.force:
        with open(manifest_path) as f:
            existing = json.load(f)
        logger.info("Question audio exists (%d clips). Use --force to regenerate.",
                     len(existing.get("questions", [])))
        return

    fixture_dir.mkdir(parents=True, exist_ok=True)

    # Combine mid-meeting and post-meeting questions
    all_questions = []

    for i, mq in enumerate(meeting.mid_meeting_questions):
        all_questions.append({
            "id": f"mid_{i:02d}",
            "type": "mid_meeting",
            "trigger_minute": mq.trigger_after_minute,
            "text": mq.question,
            "ground_truth": mq.ground_truth,
        })

    for pq in meeting.post_meeting_questions:
        all_questions.append({
            "id": pq.question_id,
            "type": "post_meeting",
            "text": pq.question,
            "ground_truth": pq.ground_truth,
            "category": pq.category,
        })

    manifest_questions = []
    total_bytes = 0

    for q in all_questions:
        filename = f"{q['id']}.pcm"
        pcm_path = fixture_dir / filename

        if pcm_path.exists() and not args.force:
            pcm_bytes = pcm_path.read_bytes()
        else:
            logger.info("[%s] Generating: %s", q["id"], q["text"][:60])
            pcm_bytes = await generate_tts(q["text"], QUESTION_VOICE)
            pcm_path.write_bytes(pcm_bytes)

        duration_ms = len(pcm_bytes) / (SAMPLE_RATE * SAMPLE_WIDTH) * 1000
        total_bytes += len(pcm_bytes)

        manifest_questions.append({
            **q,
            "filename": filename,
            "size_bytes": len(pcm_bytes),
            "duration_ms": round(duration_ms, 1),
        })

    manifest = {
        "voice": QUESTION_VOICE,
        "tts_model": "tts-1-hd",
        "total_questions": len(manifest_questions),
        "audio_format": {
            "encoding": "signed 16-bit PCM (linear)",
            "sample_rate_hz": SAMPLE_RATE,
            "bit_depth": 16,
            "byte_order": "little-endian",
            "channels": 1,
        },
        "questions": manifest_questions,
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    total_min = sum(q["duration_ms"] for q in manifest_questions) / 60000
    logger.info("")
    logger.info("========================================")
    logger.info("  Question audio generated!")
    logger.info("  Path:      %s", fixture_dir)
    logger.info("  Questions: %d (%d mid, %d post)",
                len(manifest_questions),
                sum(1 for q in manifest_questions if q["type"] == "mid_meeting"),
                sum(1 for q in manifest_questions if q["type"] == "post_meeting"))
    logger.info("  Duration:  %.1f min of audio", total_min)
    logger.info("  Format:    PCM16LE, 24kHz, mono, 16-bit")
    logger.info("========================================")


if __name__ == "__main__":
    asyncio.run(main())
