#!/usr/bin/env python3
"""Render debate audio with Kokoro TTS. Three modes plus a legacy default.

Modes:
    --warmup    Load the Kokoro model (downloading the ~330 MB checkpoint
                on first run), synthesise a 1-second test buffer, exit.
                Called at Phase A right after Batch 4 model picker so any
                missing-dep / no-network failure surfaces BEFORE the debate.
    --segment <NN>
                Render one per-break audio segment for stage NN: covers
                from the prior break-point (exclusive) to NN's end
                (inclusive of clarifying round + audience round). Reads
                the relevant slice of transcript.md. Writes
                debate_events/<slug>/audio_break_<NN>.mp3 (96 kbps).
                Idempotent — overwrites if re-run (e.g. after audience).
    --final     Concatenate the spoken disclaimer + filled methodology
                template + every audio_break_<NN>.mp3 in numerical order
                + journalist articles audio → recording.mp3. Updates
                recording.timings.json with cumulative offsets.

Default (no mode flag): legacy one-shot — reads full_debate.md, skips the
Contents / Format-table blocks, prepends the disclaimer + spoken
methodology, voices everything. Used by §7's in-flight handoff (sessions
that finished before per-segment rendering existed).

Dependencies (loaded lazily inside functions so --help works without them):
    pip install kokoro soundfile pydub
    brew install ffmpeg
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import fire
from _common import atomic_write_json, atomic_write_text  # noqa: F401

DEFAULT_BITRATE = "96k"
KOKORO_LANG = "a"  # American English; switch to "b" for British if needed.
MISSING_DEPS_HINT = (
    "Install: bash scripts/helper_scripts/run_conda_bash.sh -- pip install "
    "kokoro soundfile pydub. ffmpeg: brew install ffmpeg."
)


def _check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(f"ffmpeg not on PATH. {MISSING_DEPS_HINT}")


def _import_kokoro():
    try:
        from kokoro import KPipeline  # type: ignore

        return KPipeline
    except ImportError as exc:
        raise RuntimeError(f"kokoro not installed ({exc}). {MISSING_DEPS_HINT}") from exc


def _import_audio_libs():
    try:
        import numpy as np  # type: ignore
        import soundfile as sf  # type: ignore
        from pydub import AudioSegment  # type: ignore

        return np, sf, AudioSegment
    except ImportError as exc:
        raise RuntimeError(f"audio libs not installed ({exc}). {MISSING_DEPS_HINT}") from exc


def _load_voice_map(event_dir: Path) -> dict[str, str]:
    """Voice map persisted by Phase A Batch 4.5 voice picker."""
    path = event_dir / "voice_map.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path} — Phase A Batch 4.5 voice picker should have written it.")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_team(event_dir: Path) -> dict:
    path = event_dir / "team.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path} — B5_pre should have written it. Run team-spawn first.")
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class Utterance:
    """One voiced line: speaker key + body text."""

    speaker: str  # voice_map key: A/B/C/Moderator/Audience/Journalist
    text: str


@dataclass
class TimingEntry:
    """One row in `recording.timings.json::segments[]`."""

    t_seconds: float
    speaker: str
    voice: str
    words: int
    text_preview: str


@dataclass
class TimingsLog:
    """Accumulator for `recording.timings.json` written by --segment/--final."""

    backend: str = "kokoro"
    voice_map: dict[str, str] = field(default_factory=dict)
    total_seconds: float = 0.0
    chapters: list[dict] = field(default_factory=list)
    segments: list[TimingEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to a JSON-ready dict with rounded offsets."""
        return {
            "generated_at": _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "backend": self.backend,
            "voice_map": self.voice_map,
            "total_seconds": round(self.total_seconds, 3),
            "chapters": self.chapters,
            "segments": [
                {
                    "t_seconds": round(s.t_seconds, 3),
                    "speaker": s.speaker,
                    "voice": s.voice,
                    "words": s.words,
                    "text_preview": s.text_preview,
                }
                for s in self.segments
            ],
        }


def _slot_to_speaker_key(team: dict, surname: str) -> str | None:
    """Map a surname found in the transcript prefix back to a voice_map key."""
    for slot in ("A", "B", "C"):
        if team.get(slot, {}).get("name") == surname:
            return slot
    if surname == "Moderator":
        return "Moderator"
    if surname == "Journalist":
        return "Journalist"
    if surname == "Audience":
        return "Audience"
    return None


# Patterns for line-by-line transcript parsing.
# A surname token: capitalised, allowing internal spaces/apostrophes/hyphens
# (so "Martinez Arias" or "O'Connor-Smith" are both one surname).
_SURNAME = r"[A-Z][A-Za-z'\- ]+?"
# Plain "<Surname>: body".
SPEAKER_PREFIX = re.compile(rf"^({_SURNAME}):\s+(.+)$")
# Scientist responding to an audience-question or a clarifying-question round
# (per run-debate/SKILL.md C1 step 3.4 + C2 step 3): "<Surname> (responding to
# <asker>): <body>". Match BEFORE SPEAKER_PREFIX since the bare regex would
# otherwise grab "<Surname>" through the open paren as a literal name.
SPEAKER_RESPONSE = re.compile(rf"^({_SURNAME}) \(responding to [^)]+\):\s+(.+)$")
# Audience interjection block (Moderator-owned write — scientists never emit
# this prefix; see decision #20).
AUDIENCE_BLOCK = re.compile(r"^\*\*Audience:\*\*\s+(.+)$")
# Clarifying-question round block (per FORMAT.md §Clarifying-question rounds).
CLARIFY_BLOCK = re.compile(rf"^\*\*({_SURNAME}) → ({_SURNAME}) \(clarifying\):\*\*\s+(.+)$")
# Stage heading — H2 in transcript.md, H3 after compose_full_event H2→H3
# demotion. Accept any of em-dash, en-dash, or plain hyphen-minus so the
# parser is tolerant of whatever the appending agent / compose script emits.
STAGE_HEADING = re.compile(r"^#{2,3} Stage (\d+[a-z]?) [—–-]")


def _parse_utterances(text: str, team: dict) -> list[Utterance]:
    """Walk transcript-style text line-by-line; produce voiced utterances.

    Headings + structural markup are dropped (they'd become chapter markers
    only). Anything we can't attribute is voiced by the section's current
    speaker (default Moderator).
    """
    utterances: list[Utterance] = []
    current_speaker: str = "Moderator"
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            body = " ".join(buffer).strip()
            if body:
                utterances.append(Utterance(current_speaker, body))
            buffer.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            flush()
            continue
        # Drop headings (chapter markers, not voiced).
        if line.startswith("#"):
            flush()
            # Promote H3 ### <Surname> (Presenter A) blocks → set current_speaker.
            m = re.match(r"^#{3,} (.+?) \((Presenter [AB]|Reviewer)\)", line)
            if m:
                surname = m.group(1).strip()
                key = _slot_to_speaker_key(team, surname)
                if key is not None:
                    current_speaker = key
            continue
        # Skip blockquotes, table rows, code fences, TOC list items.
        if line.startswith(("|", ">", "```", "<!--", "    -", "- [")):
            continue

        m = CLARIFY_BLOCK.match(line)
        if m:
            flush()
            asker, speaker, body = m.group(1), m.group(2), m.group(3)
            akey = _slot_to_speaker_key(team, asker)
            if akey:
                utterances.append(Utterance(akey, f"Clarifying question to {speaker}: {body}"))
            current_speaker = _slot_to_speaker_key(team, speaker) or current_speaker
            continue
        m = AUDIENCE_BLOCK.match(line)
        if m:
            flush()
            utterances.append(Utterance("Audience", m.group(1)))
            continue
        # MUST run BEFORE SPEAKER_PREFIX — "Briscoe (responding to Arias): ..."
        # would otherwise be partially consumed by SPEAKER_PREFIX's lazy ":\s+"
        # capture, attributing the body to the wrong speaker.
        m = SPEAKER_RESPONSE.match(line)
        if m:
            flush()
            surname, body = m.group(1).strip(), m.group(2)
            key = _slot_to_speaker_key(team, surname)
            if key is not None:
                current_speaker = key
                utterances.append(Utterance(key, body))
                continue
            # Unknown surname — still drop the parenthetical prefix so it
            # isn't voiced literally, voice body under prior current_speaker.
            buffer.append(body)
            continue
        m = SPEAKER_PREFIX.match(line)
        if m:
            flush()
            surname, body = m.group(1).strip(), m.group(2)
            key = _slot_to_speaker_key(team, surname)
            if key is not None:
                current_speaker = key
                utterances.append(Utterance(key, body))
                continue
            # Unknown surname (e.g. third-party named in body) — voice the body
            # under current_speaker without the prefix, rather than silently
            # corrupting attribution by buffering "Pearl: causation is..." as
            # if the prior speaker said it.
            buffer.append(body)
            continue
        # Plain text — buffer under current_speaker.
        buffer.append(line)
    flush()
    return utterances


def _synth_kokoro(text: str, voice: str, *, np, sf, pipeline) -> object:
    """Synthesize one utterance to an in-memory waveform (numpy float32)."""
    audio_chunks = []
    for _, _, audio in pipeline(text, voice=voice):
        audio_chunks.append(audio)
    if not audio_chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(audio_chunks).astype("float32")


def _wave_to_segment(wave, *, sr: int, np, sf, AudioSegment) -> object:
    """Convert a float32 mono waveform to a pydub AudioSegment via temp WAV."""
    import io

    buf = io.BytesIO()
    sf.write(buf, wave, sr, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return AudioSegment.from_file(buf, format="wav")


def _voice_for(speaker_key: str, voice_map: dict[str, str]) -> str:
    voice = voice_map.get(speaker_key)
    if not voice:
        raise KeyError(
            f"voice_map.json missing entry for speaker key '{speaker_key}' (known keys: {sorted(voice_map.keys())})"
        )
    return voice


def _render_utterances(
    utterances: list[Utterance],
    voice_map: dict[str, str],
    *,
    pipeline,
    np,
    sf,
    AudioSegment,
    sr: int = 24000,
    timings: TimingsLog | None = None,
    cursor_offset_ms: int = 0,
) -> object:
    """Render a list of utterances to a single concatenated AudioSegment.

    `cursor_offset_ms` is the absolute time (in ms) the first utterance of this
    batch starts at within the final recording. Callers that invoke this
    multiple times for the same `timings` log MUST pass the running total
    duration of audio rendered so far, otherwise the recorded `t_seconds`
    values restart from 0 on each call and overlap.
    """
    out = AudioSegment.silent(duration=0)
    cursor_ms = cursor_offset_ms
    for utt in utterances:
        voice = _voice_for(utt.speaker, voice_map)
        wave = _synth_kokoro(utt.text, voice, np=np, sf=sf, pipeline=pipeline)
        if wave.size == 0:
            continue
        seg = _wave_to_segment(wave, sr=sr, np=np, sf=sf, AudioSegment=AudioSegment)
        if timings is not None:
            timings.segments.append(
                TimingEntry(
                    t_seconds=cursor_ms / 1000.0,
                    speaker=utt.speaker,
                    voice=voice,
                    words=len(utt.text.split()),
                    text_preview=utt.text[:120],
                )
            )
        out += seg
        cursor_ms += len(seg)
        out += AudioSegment.silent(duration=180)  # brief pause between utterances
        cursor_ms += 180
    if timings is not None:
        timings.total_seconds = max(timings.total_seconds, cursor_ms / 1000.0)
    return out


def _segment_slice(transcript_text: str, segment_n: int) -> str:
    """Return the lines of transcript.md covering segment <NN>.

    Segment NN starts after the previous break-point heading (exclusive)
    and ends at the next break-point heading (exclusive). Break-points:
    1, 2, 4, 6, 7, 8, 9, 10. For 8 / 10 the segment includes 8a+8b /
    10a+10b plus any audience response.
    """
    breaks = [1, 2, 4, 6, 7, 8, 9, 10]
    if segment_n not in breaks:
        raise ValueError(f"segment_n={segment_n} not a break-point (allowed: {breaks})")
    # Walk lines; track currently-active stage label (extracted from H2/H3).
    lines = transcript_text.splitlines(keepends=True)
    out: list[str] = []
    capturing = False
    prev_break_idx = breaks.index(segment_n) - 1
    prev_break_stage = breaks[prev_break_idx] if prev_break_idx >= 0 else 0

    for raw in lines:
        m = STAGE_HEADING.match(raw.rstrip())
        if m:
            label = m.group(1)
            # Extract integer stage from label like "8a" -> 8.
            stage_int = int(re.match(r"\d+", label).group(0))
            if stage_int > prev_break_stage and stage_int <= segment_n:
                capturing = True
            elif stage_int > segment_n:
                capturing = False
                break
        if capturing:
            out.append(raw)
    return "".join(out)


def _disclaimer_text() -> str:
    return (
        "Disclaimer. The following audio is an AI-reconstructed scientific debate. "
        "The voices are stock text-to-speech voices, gender-matched to each speaker where "
        "possible. The content represents what each named scientist might have argued, "
        "based on extensive briefings from their published work — it is not a verbatim "
        "transcript of anything they actually said."
    )


def _methodology_text(event_dir: Path, inputs: dict, team: dict) -> str:
    template_path = Path(__file__).parent / "_methodology_template.md"
    template = template_path.read_text(encoding="utf-8")
    total_minutes = inputs.get("debate", {}).get("total_minutes", 80)
    topic = inputs.get("topic", "the debate topic")
    cast_lines = " and ".join([team[s]["name"] for s in ("A", "B", "C")])
    return template.format(
        cast_lines=cast_lines,
        topic=topic,
        total_minutes=total_minutes,
    )


def _strip_skip_blocks(text: str) -> str:
    """Excise the ## Contents block and Format-table block (decision #4.9)."""
    # ## Contents → next H2 (or EOF)
    text = re.sub(r"^## Contents.*?(?=^## |\Z)", "", text, flags=re.MULTILINE | re.DOTALL)
    # Format-table: a header line `| # | Stage | Speaker | Words | Audience…`
    # plus the table that follows (up to first blank line after table).
    text = re.sub(
        r"^\| # \| Stage \|.*?\n(\|.*\n)+\n",
        "",
        text,
        flags=re.MULTILINE,
    )
    return text


def warmup(*, event_dir: str = ".") -> dict[str, str]:
    """Load Kokoro model + synth 1-sec test buffer. Fail fast on missing deps."""
    _check_ffmpeg()
    KPipeline = _import_kokoro()
    np, sf, AudioSegment = _import_audio_libs()
    print("Loading Kokoro pipeline (downloads ~330 MB on first run) …", file=sys.stderr)
    pipeline = KPipeline(lang_code=KOKORO_LANG)
    wave = _synth_kokoro("Audio system ready.", "af_sarah", np=np, sf=sf, pipeline=pipeline)
    duration_s = wave.size / 24000.0 if wave.size else 0.0
    print(f"OK. Test buffer length: {duration_s:.2f}s.", file=sys.stderr)
    return {"status": "warmup-ok", "test_buffer_s": f"{duration_s:.3f}"}


def segment(*, event_dir: str, segment: int, bitrate: str = DEFAULT_BITRATE) -> dict[str, str]:
    """Render one per-break audio segment to audio_break_<NN>.mp3."""
    _check_ffmpeg()
    KPipeline = _import_kokoro()
    np, sf, AudioSegment = _import_audio_libs()
    event_path = Path(event_dir).resolve()
    transcript_text = (event_path / "transcript.md").read_text(encoding="utf-8")
    team = _load_team(event_path)
    voice_map = _load_voice_map(event_path)

    slice_text = _segment_slice(transcript_text, segment)
    utterances = _parse_utterances(slice_text, team)
    if not utterances:
        raise RuntimeError(
            f"No utterances parsed for segment {segment} from transcript.md "
            f"({len(slice_text)} bytes of slice). Likely causes: stage NN "
            f"isn't appended yet, stage heading uses an unexpected dash "
            f"glyph, or transcript.md is empty for this range."
        )
    pipeline = KPipeline(lang_code=KOKORO_LANG)
    audio = _render_utterances(utterances, voice_map, pipeline=pipeline, np=np, sf=sf, AudioSegment=AudioSegment)
    out_path = event_path / f"audio_break_{segment:02d}.mp3"
    audio.export(out_path, format="mp3", bitrate=bitrate)
    return {"audio_path": str(out_path), "utterances": str(len(utterances)), "ms": str(len(audio))}


def final(*, event_dir: str, bitrate: str = DEFAULT_BITRATE) -> dict[str, str]:
    """Concatenate preamble + per-break segments + articles → recording.mp3.

    Preamble = disclaimer + filled methodology template; segments = every
    audio_break_<NN>.mp3 on disk in numerical order; articles voiced last.
    """
    _check_ffmpeg()
    KPipeline = _import_kokoro()
    np, sf, AudioSegment = _import_audio_libs()
    event_path = Path(event_dir).resolve()
    team = _load_team(event_path)
    voice_map = _load_voice_map(event_path)
    inputs = json.loads((event_path / "inputs.json").read_text(encoding="utf-8"))

    timings = TimingsLog(voice_map=voice_map)
    pipeline = KPipeline(lang_code=KOKORO_LANG)

    # Preamble: disclaimer + methodology — voiced as Moderator.
    preamble_utts = [
        Utterance("Moderator", _disclaimer_text()),
        Utterance("Moderator", _methodology_text(event_path, inputs, team)),
    ]
    audio = _render_utterances(
        preamble_utts,
        voice_map,
        pipeline=pipeline,
        np=np,
        sf=sf,
        AudioSegment=AudioSegment,
        timings=timings,
    )
    timings.chapters.append({"t_seconds": 0.0, "level": 1, "text": "Preamble"})

    # Concatenate per-break segments in numerical order.
    for seg_n in (1, 2, 4, 6, 7, 8, 9, 10):
        seg_path = event_path / f"audio_break_{seg_n:02d}.mp3"
        if not seg_path.exists():
            continue
        seg_audio = AudioSegment.from_file(seg_path, format="mp3")
        timings.chapters.append({"t_seconds": round(len(audio) / 1000.0, 3), "level": 2, "text": f"Stage {seg_n}"})
        audio += seg_audio

    # Journalist articles voiced at end. Thread `timings` with the running
    # cursor so per-utterance offsets stay monotonic across the whole
    # recording.
    for fname, label in [
        ("article_same_field.md", "Article for the same field"),
        ("article_broader_field.md", "Article for adjacent fields"),
        ("article_general_stem.md", "Article for general STEM readers"),
    ]:
        path = event_path / fname
        if not path.exists():
            continue
        timings.chapters.append({"t_seconds": round(len(audio) / 1000.0, 3), "level": 2, "text": label})
        body = path.read_text(encoding="utf-8")
        utts = [Utterance("Journalist", line) for line in body.split("\n\n") if line.strip()]
        audio += _render_utterances(
            utts,
            voice_map,
            pipeline=pipeline,
            np=np,
            sf=sf,
            AudioSegment=AudioSegment,
            timings=timings,
            cursor_offset_ms=len(audio),
        )

    out_audio = event_path / "recording.mp3"
    out_timings = event_path / "recording.timings.json"
    # mp3: write to a temp path then os.replace so a crash mid-export doesn't
    # leave a partial recording.mp3 lying around.
    tmp_audio = out_audio.with_name(out_audio.name + ".partial")
    audio.export(tmp_audio, format="mp3", bitrate=bitrate)
    tmp_audio.replace(out_audio)
    timings.total_seconds = len(audio) / 1000.0
    atomic_write_json(out_timings, timings.to_dict())

    return {
        "recording": str(out_audio),
        "timings": str(out_timings),
        "total_seconds": f"{timings.total_seconds:.1f}",
    }


def legacy(*, event_dir: str, bitrate: str = DEFAULT_BITRATE) -> dict[str, str]:
    """One-shot mode for §7 in-flight handoff — reads full_debate.md end-to-end.

    Applies skip rules (drops Contents + Format-table blocks), prepends the
    disclaimer + methodology preamble, then voices every utterance in one go.
    Used by sessions that finished before per-segment rendering existed.
    """
    _check_ffmpeg()
    KPipeline = _import_kokoro()
    np, sf, AudioSegment = _import_audio_libs()
    event_path = Path(event_dir).resolve()
    full_debate = event_path / "full_debate.md"
    if not full_debate.exists():
        raise FileNotFoundError(f"Missing {full_debate} — run compose_full_event.py first.")
    team = _load_team(event_path)
    voice_map = _load_voice_map(event_path)
    inputs = json.loads((event_path / "inputs.json").read_text(encoding="utf-8"))

    text = full_debate.read_text(encoding="utf-8")
    text = _strip_skip_blocks(text)

    pipeline = KPipeline(lang_code=KOKORO_LANG)
    timings = TimingsLog(voice_map=voice_map)
    preamble = [
        Utterance("Moderator", _disclaimer_text()),
        Utterance("Moderator", _methodology_text(event_path, inputs, team)),
    ]
    audio = _render_utterances(
        preamble,
        voice_map,
        pipeline=pipeline,
        np=np,
        sf=sf,
        AudioSegment=AudioSegment,
        timings=timings,
    )
    body_utts = _parse_utterances(text, team)
    audio += _render_utterances(
        body_utts,
        voice_map,
        pipeline=pipeline,
        np=np,
        sf=sf,
        AudioSegment=AudioSegment,
        timings=timings,
        cursor_offset_ms=len(audio),
    )

    out_audio = event_path / "recording.mp3"
    out_timings = event_path / "recording.timings.json"
    tmp_audio = out_audio.with_name(out_audio.name + ".partial")
    audio.export(tmp_audio, format="mp3", bitrate=bitrate)
    tmp_audio.replace(out_audio)
    timings.total_seconds = len(audio) / 1000.0
    atomic_write_json(out_timings, timings.to_dict())
    return {
        "recording": str(out_audio),
        "timings": str(out_timings),
        "total_seconds": f"{timings.total_seconds:.1f}",
    }


def main(
    *,
    event_dir: str = ".",
    warmup: bool = False,
    segment: int | None = None,
    final: bool = False,
    bitrate: str = DEFAULT_BITRATE,
    backend: str = "kokoro",
) -> dict[str, str]:
    """Dispatch to the selected mode.

    Backend defaults to ``kokoro``; ``f5tts`` is a stub that raises
    NotImplementedError (Phase 2 voice-cloning — see plan §4 advisory).
    """
    if backend == "f5tts":
        raise NotImplementedError("Phase 2: voice cloning — see plan §4 advisory.")
    if backend != "kokoro":
        raise ValueError(f"Unknown backend: {backend!r}")
    if warmup:
        return globals()["warmup"](event_dir=event_dir)
    if segment is not None:
        return globals()["segment"](event_dir=event_dir, segment=segment, bitrate=bitrate)
    if final:
        return globals()["final"](event_dir=event_dir, bitrate=bitrate)
    return legacy(event_dir=event_dir, bitrate=bitrate)


if __name__ == "__main__":
    fire.Fire(main)
