"""Audio utilities for voice benchmarking.

Handles:
- TTS generation (text → PCM16 files) — run ONCE via generate_audio.py
- Loading pre-generated audio from a fixed directory
- PCM16 encoding/chunking for WebSocket streaming
- Transcription accuracy comparison (WER)

IMPORTANT: Audio is generated once and saved to a fixed path (audio_fixtures/).
Experiments always load from that path — never generate on the fly.
This ensures every run uses the exact same audio bytes.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from common.config import ROOT_DIR, setup_logging

logger = setup_logging("audio")

SAMPLE_RATE = 24000  # both OpenAI and Grok use 24kHz
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit PCM
CHUNK_DURATION_MS = 100  # send 100ms chunks at a time
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)

# Fixed path for audio fixtures — generated once, used by all runs
AUDIO_FIXTURES_DIR = ROOT_DIR / "audio_fixtures"


def get_fixture_dir(meeting_name: str = "realistic_meeting") -> Path:
    """Get the fixture directory for a named meeting."""
    return AUDIO_FIXTURES_DIR / meeting_name


def load_meeting_audio(meeting_name: str = "realistic_meeting") -> list[dict]:
    """Load pre-generated audio from the fixtures directory.

    Reads the manifest.json and all PCM files.
    Raises FileNotFoundError if audio hasn't been generated yet.

    Returns:
        List of {"speaker", "text", "minute", "audio_path", "pcm16_bytes", "duration_ms"}
    """
    fixture_dir = get_fixture_dir(meeting_name)
    manifest_path = fixture_dir / "manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Audio fixtures not found at {fixture_dir}/\n"
            f"Generate them first:\n"
            f"  python3 generate_audio.py --meeting {meeting_name}\n"
            f"This only needs to be done once."
        )

    with open(manifest_path) as f:
        manifest = json.load(f)

    results = []
    for entry in manifest["lines"]:
        pcm_path = fixture_dir / entry["filename"]
        if not pcm_path.exists():
            raise FileNotFoundError(f"Missing audio file: {pcm_path}")

        pcm_bytes = pcm_path.read_bytes()
        duration_ms = len(pcm_bytes) / (SAMPLE_RATE * SAMPLE_WIDTH) * 1000

        results.append({
            "speaker": entry["speaker"],
            "text": entry["text"],
            "minute": entry["minute"],
            "audio_path": str(pcm_path),
            "pcm16_bytes": pcm_bytes,
            "duration_ms": duration_ms,
        })

    logger.info(
        "Loaded %d audio clips from %s (total: %.1f min audio)",
        len(results), fixture_dir,
        sum(r["duration_ms"] for r in results) / 60000,
    )
    return results


def load_question_audio(meeting_name: str = "meeting_1hr") -> dict[str, dict]:
    """Load pre-generated question audio.

    Returns dict keyed by question ID:
        {"mid_00": {"text": ..., "pcm16_bytes": ..., "duration_ms": ...}, ...}

    Raises FileNotFoundError if not generated yet.
    """
    fixture_dir = AUDIO_FIXTURES_DIR / (meeting_name + "_questions")
    manifest_path = fixture_dir / "manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Question audio not found at {fixture_dir}/\n"
            f"Generate first: python3 generate_question_audio.py"
        )

    with open(manifest_path) as f:
        manifest = json.load(f)

    results = {}
    for entry in manifest["questions"]:
        pcm_path = fixture_dir / entry["filename"]
        pcm_bytes = pcm_path.read_bytes()
        duration_ms = len(pcm_bytes) / (SAMPLE_RATE * SAMPLE_WIDTH) * 1000
        results[entry["id"]] = {
            "text": entry["text"],
            "ground_truth": entry.get("ground_truth", ""),
            "type": entry["type"],
            "pcm16_bytes": pcm_bytes,
            "duration_ms": duration_ms,
        }

    logger.info("Loaded %d question audio clips from %s", len(results), fixture_dir)
    return results


def pcm16_to_base64_chunks(pcm_bytes: bytes) -> list[str]:
    """Split PCM16 audio into base64-encoded chunks for WebSocket streaming.

    Each chunk is ~100ms of audio.
    """
    chunk_size = CHUNK_SAMPLES * SAMPLE_WIDTH  # bytes per chunk
    chunks = []
    for offset in range(0, len(pcm_bytes), chunk_size):
        chunk = pcm_bytes[offset:offset + chunk_size]
        chunks.append(base64.b64encode(chunk).decode("ascii"))
    return chunks


def compute_wer(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate between reference and hypothesis.

    WER = (substitutions + insertions + deletions) / words_in_reference
    Lower is better. 0.0 = perfect transcription.
    """
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    n = len(ref_words)
    m = len(hyp_words)
    dp = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],      # deletion
                    dp[i][j - 1],      # insertion
                    dp[i - 1][j - 1],  # substitution
                )

    return dp[n][m] / n


def compute_transcription_accuracy(reference: str, hypothesis: str) -> dict:
    """Compute multiple transcription accuracy metrics."""
    wer = compute_wer(reference, hypothesis)

    ref_lower = reference.lower().strip()
    hyp_lower = hypothesis.lower().strip()

    ref_words = set(ref_lower.split())
    hyp_words = set(hyp_lower.split())
    common = ref_words & hyp_words
    word_overlap = len(common) / len(ref_words) if ref_words else 0.0

    return {
        "wer": round(wer, 3),
        "word_overlap": round(word_overlap, 3),
        "ref_word_count": len(ref_lower.split()),
        "hyp_word_count": len(hyp_lower.split()),
    }
