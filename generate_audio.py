#!/usr/bin/env python3
"""One-time audio fixture generator.

Generates TTS audio for all meeting lines and saves them to audio_fixtures/.
Run this ONCE. All experiment runs will load from the same fixed files.

Usage:
    python3 generate_audio.py
    python3 generate_audio.py --meeting realistic_meeting
    python3 generate_audio.py --meeting realistic_meeting --force

The output is:
    audio_fixtures/realistic_meeting/
        manifest.json           ← index of all lines + metadata
        line_0000_Alice.pcm     ← raw PCM16 24kHz mono
        line_0001_Bob.pcm
        ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common.audio import AUDIO_FIXTURES_DIR, SAMPLE_RATE, SAMPLE_WIDTH, get_fixture_dir
from common.config import setup_logging

logger = setup_logging("generate_audio")

# Speaker → OpenAI TTS voice mapping
VOICE_MAP = {
    "Alice": "nova",
    "Bob": "echo",
    "Carol": "shimmer",
    "David": "onyx",
}
DEFAULT_VOICE = "alloy"


async def generate_tts(text: str, voice: str) -> bytes:
    """Call OpenAI TTS API to generate PCM16 audio."""
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
    parser = argparse.ArgumentParser(description="Generate audio fixtures for benchmarks")
    parser.add_argument(
        "--meeting",
        default="realistic_meeting",
        help="Meeting name (default: realistic_meeting)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if files already exist",
    )
    args = parser.parse_args()

    fixture_dir = get_fixture_dir(args.meeting)
    manifest_path = fixture_dir / "manifest.json"

    if manifest_path.exists() and not args.force:
        with open(manifest_path) as f:
            existing = json.load(f)
        logger.info(
            "Audio fixtures already exist at %s (%d lines). Use --force to regenerate.",
            fixture_dir, len(existing["lines"]),
        )
        return

    # Load the meeting script
    if args.meeting == "meeting_1hr":
        from experiments.e05_realtime_session_1hr.meeting_1hr import generate_meeting_1hr
        meeting = generate_meeting_1hr()
    else:
        from experiments.e05_realtime_session_1hr.realistic_meeting import generate_realistic_meeting
        meeting = generate_realistic_meeting()

    fixture_dir.mkdir(parents=True, exist_ok=True)

    manifest_lines = []
    total_bytes = 0

    for i, line in enumerate(meeting.lines):
        voice = VOICE_MAP.get(line.speaker, DEFAULT_VOICE)
        filename = f"line_{i:04d}_{line.speaker}.pcm"
        pcm_path = fixture_dir / filename

        if pcm_path.exists() and not args.force:
            pcm_bytes = pcm_path.read_bytes()
            logger.debug("Exists: %s", filename)
        else:
            logger.info(
                "[%d/%d] Generating [%s/%s]: %s",
                i + 1, len(meeting.lines), line.speaker, voice, line.text[:50],
            )
            pcm_bytes = await generate_tts(line.text, voice)
            pcm_path.write_bytes(pcm_bytes)

        duration_ms = len(pcm_bytes) / (SAMPLE_RATE * SAMPLE_WIDTH) * 1000
        total_bytes += len(pcm_bytes)

        manifest_lines.append({
            "index": i,
            "speaker": line.speaker,
            "voice": voice,
            "text": line.text,
            "minute": line.minute,
            "filename": filename,
            "size_bytes": len(pcm_bytes),
            "duration_ms": round(duration_ms, 1),
        })

    # Write manifest
    manifest = {
        "meeting_name": args.meeting,
        "meeting_title": meeting.title,
        "total_lines": len(manifest_lines),
        "total_audio_ms": round(sum(l["duration_ms"] for l in manifest_lines), 1),
        "total_size_bytes": total_bytes,
        "audio_format": {
            "encoding": "signed 16-bit PCM (linear)",
            "sample_rate_hz": SAMPLE_RATE,
            "channels": 1,
            "bit_depth": 16,
            "byte_order": "little-endian",
            "bytes_per_sample": SAMPLE_WIDTH,
            "container": "raw (headerless)",
            "notes": "OpenAI TTS API returns raw PCM16LE at 24kHz mono. "
                     "Both OpenAI and Grok realtime APIs expect this exact format. "
                     "To play: ffplay -f s16le -ar 24000 -ac 1 <file>.pcm",
        },
        "tts_model": "tts-1-hd",
        "tts_speed": 1.0,
        "voice_map": VOICE_MAP,
        "lines": manifest_lines,
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    total_min = manifest["total_audio_ms"] / 60000
    total_mb = total_bytes / (1024 * 1024)

    logger.info("")
    logger.info("========================================")
    logger.info("  Audio fixtures generated!")
    logger.info("  Path:       %s", fixture_dir)
    logger.info("  Lines:      %d", len(manifest_lines))
    logger.info("  Duration:   %.1f min of audio", total_min)
    logger.info("  Size:       %.1f MB", total_mb)
    logger.info("  Format:     PCM16LE, 24kHz, mono, 16-bit")
    logger.info("  TTS model:  tts-1-hd (speed=1.0)")
    logger.info("  Manifest:   %s", manifest_path)
    logger.info("========================================")
    logger.info("")
    logger.info("Play a file:  ffplay -f s16le -ar 24000 -ac 1 %s/line_0000_Alice.pcm", fixture_dir)
    logger.info("These files are permanent. All runs will use them.")
    logger.info("To regenerate: python3 generate_audio.py --force")


if __name__ == "__main__":
    asyncio.run(main())
