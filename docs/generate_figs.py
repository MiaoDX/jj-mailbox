#!/usr/bin/env python3
"""Generate terminal figures (SVG + GIF) for the jj-mailbox README.

Re-run when tests or protocol change:
    uv run python docs/generate_figs.py

Requires: Pillow (for GIF generation), jj, jj-mailbox CLI
Falls back to cached content if tests can't run.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
BIN = str(REPO_ROOT / "bin" / "jj-mailbox")
OUTPUT_DIR = Path(__file__).parent / "fig"

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

# ---------------------------------------------------------------------------
# Catppuccin Mocha palette
# ---------------------------------------------------------------------------
BG = "#1e1e2e"
TITLEBAR = "#313244"
TEXT = "#cdd6f4"
GREEN = "#a6e3a1"
RED = "#f38ba8"
YELLOW = "#f9e2af"
BLUE = "#89b4fa"
LAVENDER = "#b4befe"
PINK = "#f5c2e7"
TEAL = "#94e2d5"
SUBTEXT = "#a6adc8"
SURFACE = "#45475a"

TL_RED = "#ff5f57"
TL_YELLOW = "#febc2e"
TL_GREEN = "#28c840"

# ---------------------------------------------------------------------------
# Layout constants (shared)
# ---------------------------------------------------------------------------
SVG_FONT = "Menlo, Monaco, 'Courier New', monospace"
SVG_FONT_SIZE = 13
LINE_HEIGHT = 20
CHAR_WIDTH = 7.8
PADDING_X = 20
PADDING_Y = 16
TITLEBAR_H = 38
CORNER_R = 10
SVG_WIDTH = 720

GIF_WIDTH = 720
GIF_FONT_SIZE = 14
GIF_TITLE_FONT_SIZE = 13
GIF_LEFT_PAD = 20
GIF_CONTENT_Y0 = 55
GIF_BOTTOM_PAD = 20
GIF_CORNER_RADIUS = 12

CMD_HOLD = 400
GROUP_PAUSE = 1200
FINAL_HOLD = 4000

TITLE_TEXT_COLOR = SUBTEXT

# Known agent names for colorizing
AGENT_NAMES = {"planner", "researcher", "alice", "bob", "carol"}
MSG_ID_RE = re.compile(r"(msg-[0-9a-f]{8})")

# ANSI escape code stripper
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Emoji map for GIF (DejaVu Sans Mono lacks emoji glyphs)
EMOJI_REPLACEMENTS = {
    "\U0001f7e2": "*",       # 🟢 → *
    "\U0001f4ec": "",        # 📬 → skip
    "\U0001f550": "",        # 🕐 → skip
    "\U0001f4ca": "",        # 📊 → skip
    "\u2705": "[PASS]",      # ✅ → [PASS]
}


# ---------------------------------------------------------------------------
# ANSI / emoji helpers
# ---------------------------------------------------------------------------

def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def replace_emojis_for_gif(text: str) -> str:
    for emoji, replacement in EMOJI_REPLACEMENTS.items():
        text = text.replace(emoji, replacement)
    return text


# ---------------------------------------------------------------------------
# Fallback content (used when live capture fails)
# ---------------------------------------------------------------------------

FALLBACK_TEST_SUITE = [
    "=== Core CLI Tests ===",
    "--- init",
    "  PASS",
    "--- register alice",
    "  PASS",
    "--- register bob",
    "  PASS",
    "--- send",
    "  PASS",
    "--- inbox",
    "  PASS",
    "--- read",
    "  PASS",
    "--- reply",
    "  PASS",
    "--- status",
    "  PASS",
    "",
    "=== Scripted Agent Test ===",
    "--- scripted/test.py",
    "  PASS",
    "",
    "=== Comparison Benchmark ===",
    "--- comparison/benchmark.py",
    "  PASS",
    "",
    "===============================",
    "  PASS: 10  FAIL: 0",
    "===============================",
]

FALLBACK_AGENT_CONVERSATION = [
    "Level 2a: Scripted agent test",
    "",
    "Turn 1: planner \u2192 researcher: 'List 3 caching strategies.'",
    "  msg1 id: msg-2186647e",
    "Turn 2: researcher reads, replies with refs=[msg1_id]",
    "  msg2 id: msg-62bf320b",
    "  msg2 refs: ['msg-2186647e'] \u2713",
    "Turn 3: planner reads, acks with refs=[msg2_id]",
    "  msg3 id: msg-582303a7",
    "  msg3 refs: ['msg-62bf320b'] \u2713",
    "",
    "Assertions:",
    "  planner processed: 1",
    "  researcher processed: 2",
    "  shared artifact exists \u2713",
    "",
    "\u2705 Level 2a: All assertions passed!",
]

FALLBACK_MAILBOX_DEMO: list[tuple[str, list[str]]] = [
    ("cmd", ["$ jj-mailbox status"]),
    ("output", [
        "Agent Status:",
        "  alice     online   inbox: 0 new",
        "  bob       online   inbox: 1 new",
        "  carol     online   inbox: 0 new",
    ]),
    ("cmd", ["$ jj-mailbox inbox --agent bob"]),
    ("output", [
        "1 message(s) for bob:",
        "  From: alice  Subject: Research done  Time: 2026-03-11T14:30:00Z",
    ]),
    ("cmd", ["$ jj-mailbox read --agent bob"]),
    ("output", [
        "{",
        '  "version": "0.1",',
        '  "id": "msg-a1b2c3d4",',
        '  "from": "alice",',
        '  "to": "bob",',
        '  "subject": "Research done",',
        '  "body": "Found 3 caching strategies. Recommend LRU with TTL.",',
        '  "refs": [],',
        '  "timestamp": "2026-03-11T14:30:00Z"',
        "}",
    ]),
]


# ===========================================================================
# Capture functions
# ===========================================================================

def capture_test_suite() -> list[str]:
    """Run tests/run_all.py --no-llm, return stdout lines."""
    try:
        result = subprocess.run(
            [sys.executable, "tests/run_all.py", "--no-llm"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
            timeout=120,
        )
        raw = result.stdout
        if not raw.strip():
            raise RuntimeError("Empty output from run_all.py")
        lines = raw.splitlines()
        # Strip leading blank lines
        while lines and not lines[0].strip():
            lines.pop(0)
        return lines
    except Exception as e:
        print(f"  WARNING: Could not run tests: {e}")
        print(f"  Using fallback content")
        return list(FALLBACK_TEST_SUITE)


def capture_agent_conversation() -> list[str]:
    """Run tests/scripted/test.py, return stdout lines."""
    try:
        result = subprocess.run(
            [sys.executable, "tests/scripted/test.py"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
            timeout=120,
        )
        raw = result.stdout
        if not raw.strip():
            raise RuntimeError("Empty output from scripted/test.py")

        out: list[str] = []
        for ln in raw.splitlines():
            stripped = ln.strip()
            # Skip 60-char "=" separators
            if stripped and all(c == "=" for c in stripped) and len(stripped) >= 20:
                continue
            # Skip "Test repo: ..." line
            if stripped.startswith("Test repo:"):
                continue
            # Skip "Writing shared artifact" and "Artifact written" lines
            if stripped.startswith("Writing shared artifact"):
                continue
            if stripped.startswith("Artifact written:"):
                continue
            out.append(ln)

        # Strip leading/trailing blank lines
        while out and not out[0].strip():
            out.pop(0)
        while out and not out[-1].strip():
            out.pop()
        return out
    except Exception as e:
        print(f"  WARNING: Could not run scripted test: {e}")
        print(f"  Using fallback content")
        return list(FALLBACK_AGENT_CONVERSATION)


def capture_mailbox_demo() -> list[tuple[str, list[str]]]:
    """Set up temp repo, run CLI commands, return groups for GIF/SVG.

    Returns list of (kind, lines) tuples where kind is "cmd" or "output".
    """
    try:
        repo = tempfile.mkdtemp(prefix="jj-mailbox-fig-")
        env = {**os.environ, "JJ_MAILBOX_REPO": repo}

        def _run(cmd: str, extra_env: dict[str, str] | None = None) -> str:
            run_env = {**env, **(extra_env or {})}
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                env=run_env, timeout=30,
            )
            return strip_ansi(r.stdout.strip())

        try:
            # Setup
            _run(f"{BIN} init {repo}")
            _run(f"{BIN} register alice 'Research specialist'")
            _run(f"{BIN} register bob 'Code reviewer'")
            _run(f"{BIN} register carol 'QA engineer'")

            # Send a message from alice to bob
            _run(
                f'{BIN} send bob "Research done" '
                f'"Found 3 caching strategies. Recommend LRU with TTL."',
                extra_env={"JJ_MAILBOX_AGENT": "alice"},
            )

            # Capture status
            status_raw = _run(f"{BIN} status")
            # Parse status: strip the [jj-mailbox] prefix + timestamp
            status_lines: list[str] = []
            for ln in status_raw.splitlines():
                cleaned = ln.strip()
                if not cleaned:
                    continue
                # Remove "[jj-mailbox] HH:MM:SS " prefix
                prefix_match = re.match(r"^\[jj-mailbox\]\s+\S+\s+(.*)", cleaned)
                if prefix_match:
                    cleaned = prefix_match.group(1)
                status_lines.append(cleaned)

            # Capture inbox for bob
            inbox_raw = _run(
                f"{BIN} inbox bob",
                extra_env={"JJ_MAILBOX_AGENT": "bob"},
            )
            inbox_lines: list[str] = []
            for ln in inbox_raw.splitlines():
                cleaned = ln.strip()
                if not cleaned:
                    continue
                # Remove "[jj-mailbox] HH:MM:SS " prefix
                prefix_match = re.match(r"^\[jj-mailbox\]\s+\S+\s+(.*)", cleaned)
                if prefix_match:
                    cleaned = prefix_match.group(1)
                inbox_lines.append(cleaned)

            # Capture read for bob (raw JSON)
            read_raw = _run(
                f"{BIN} read bob",
                extra_env={"JJ_MAILBOX_AGENT": "bob"},
            )
            # Pretty-print the JSON
            read_lines: list[str] = []
            try:
                json_match = re.search(r"\{.*\}", read_raw, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    pretty = json.dumps(parsed, indent=2)
                    read_lines = pretty.splitlines()
                else:
                    read_lines = read_raw.splitlines()
            except json.JSONDecodeError:
                read_lines = read_raw.splitlines()

            groups: list[tuple[str, list[str]]] = [
                ("cmd", ["$ jj-mailbox status"]),
                ("output", status_lines),
                ("cmd", ["$ jj-mailbox inbox --agent bob"]),
                ("output", inbox_lines),
                ("cmd", ["$ jj-mailbox read --agent bob"]),
                ("output", read_lines),
            ]
            return groups

        finally:
            shutil.rmtree(repo, ignore_errors=True)

    except Exception as e:
        print(f"  WARNING: Could not run mailbox demo: {e}")
        print(f"  Using fallback content")
        return [tuple(g) for g in FALLBACK_MAILBOX_DEMO]


# ===========================================================================
# Colorizer (shared between SVG and GIF)
# ===========================================================================

class Span(NamedTuple):
    """A piece of text with a colour."""
    text: str
    color: str = TEXT


def _split_keep(pattern: re.Pattern[str], text: str) -> list[str]:
    """Split *text* on *pattern* but keep the matched delimiters."""
    parts: list[str] = []
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            parts.append(text[last:m.start()])
        parts.append(m.group())
        last = m.end()
    if last < len(text):
        parts.append(text[last:])
    return parts


_RICH_RE = re.compile(
    r"(?:"
    + "|".join([
        r"\b(?:" + "|".join(AGENT_NAMES) + r")\b",
        r"msg-[0-9a-f]{8}",
        r"\u2713",       # ✓
        r"\u2192",       # →
        r"\bonline\b",
        r"\[PASS\]",
        r"'\[?msg-[0-9a-f]{8}\]?'",
        r"\['msg-[0-9a-f]{8}'\]",
    ])
    + r")"
)


def colorize_line(line: str) -> list[Span]:
    """Parse a line into a list of (text, color) spans."""
    # --- prompt ---
    if line.startswith("$ "):
        return [Span("$ ", BLUE), Span(line[2:], TEXT)]

    # --- section header with === ... === ---
    stripped = line.strip()
    if stripped.startswith("===") and stripped.endswith("==="):
        return [Span(line, LAVENDER)]

    # --- separator lines (all =) ---
    if stripped and all(c == "=" for c in stripped):
        return [Span(line, SURFACE)]

    # --- dim separator with --- prefix ---
    if re.match(r"^\s*---\s+\S", line):
        # Test line: "--- test_name" followed by PASS/FAIL on next line
        return [Span(line, SUBTEXT)]

    # --- [PASS] prefix ---
    if stripped.startswith("[PASS]"):
        return [Span(line, GREEN)]

    # --- ✅ prefix ---
    if "\u2705" in line:
        return [Span(line, GREEN)]

    # --- "  PASS" / "  FAIL" standalone ---
    if stripped == "PASS":
        return [Span(line.replace("PASS", ""), TEXT), Span("PASS", GREEN)]
    if stripped == "FAIL":
        return [Span(line.replace("FAIL", ""), TEXT), Span("FAIL", RED)]

    # --- Summary line:  PASS: N  FAIL: N ---
    summary_match = re.match(r"^(\s*PASS:\s*)(\d+)(\s+FAIL:\s*)(\d+)(.*)$", line)
    if summary_match:
        pre, pass_n, mid, fail_n, rest = summary_match.groups()
        return [
            Span(pre, TEXT),
            Span(pass_n, YELLOW),
            Span(mid, TEXT),
            Span(fail_n, YELLOW),
            Span(rest, TEXT),
        ]

    # --- JSON lines ---
    json_key_match = re.match(r'^(\s*)"(\w+)"(\s*:\s*)(.*)', line)
    if json_key_match:
        indent, key, colon, rest = json_key_match.groups()
        segs = [Span(indent, TEXT), Span(f'"{key}"', TEAL), Span(colon, TEXT)]
        rest_stripped = rest.rstrip(",").rstrip()
        trailing = rest[len(rest_stripped):]
        if rest_stripped.startswith('"') and rest_stripped.endswith('"'):
            segs.append(Span(rest_stripped, YELLOW))
            segs.append(Span(trailing, TEXT))
        elif rest_stripped == "[]":
            segs.append(Span(rest_stripped, TEAL))
            segs.append(Span(trailing, TEXT))
        else:
            segs.append(Span(rest, TEXT))
        return segs
    if stripped in ("{", "}", "},"):
        return [Span(line, TEXT)]

    # --- Agent Status / Assertions header ---
    if stripped in ("Agent Status:", "Assertions:"):
        return [Span(line, LAVENDER)]

    # --- Lines with arrows, agent names, msg-ids, check marks ---
    rich = _rich_segments(line)
    if rich is not None:
        return rich

    return [Span(line, TEXT)]


def _rich_segments(line: str) -> list[Span] | None:
    """Best-effort rich coloring for lines with agent names, msg-ids, etc."""
    parts = _split_keep(_RICH_RE, line)

    if len(parts) <= 1 and not any(
        tok in line for tok in AGENT_NAMES | {"\u2713", "\u2192", "online", "msg-"}
    ):
        return None

    segs: list[Span] = []
    for part in parts:
        if part in AGENT_NAMES:
            segs.append(Span(part, LAVENDER))
        elif part == "\u2192":
            segs.append(Span(part, PINK))
        elif part == "\u2713":
            segs.append(Span(part, GREEN))
        elif part == "online":
            segs.append(Span(part, GREEN))
        elif part.startswith("[PASS]"):
            segs.append(Span(part, GREEN))
        elif MSG_ID_RE.fullmatch(part):
            segs.append(Span(part, YELLOW))
        elif "msg-" in part:
            segs.append(Span(part, TEAL))
        else:
            segs.append(Span(part, TEXT))
    return segs


# ===========================================================================
# SVG renderer
# ===========================================================================

def svg_text_spans(spans: list[Span], x: int, y: int) -> str:
    parts: list[str] = [
        f'<text x="{x}" y="{y}" font-family="{SVG_FONT}" '
        f'font-size="{SVG_FONT_SIZE}" xml:space="preserve">'
    ]
    for span in spans:
        col = escape(span.color)
        txt = escape(span.text)
        parts.append(f'<tspan fill="{col}">{txt}</tspan>')
    parts.append("</text>")
    return "".join(parts)


def traffic_lights_svg(cx_start: int, cy: int, r: int = 6, gap: int = 20) -> str:
    circles = [
        (TL_RED, cx_start),
        (TL_YELLOW, cx_start + gap),
        (TL_GREEN, cx_start + gap * 2),
    ]
    return "\n".join(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" />'
        for color, cx in circles
    )


def render_svg(lines: list[str], title: str = "miaodx@jj-mailbox: ~") -> str:
    """Render a list of text lines into a macOS-style terminal SVG string."""
    # Colorize all lines
    content_lines = [colorize_line(ln) for ln in lines]
    n_lines = len(content_lines)

    width = SVG_WIDTH
    content_h = PADDING_Y + n_lines * LINE_HEIGHT + PADDING_Y
    height = TITLEBAR_H + content_h

    lines_svg: list[str] = []
    for i, spans in enumerate(content_lines):
        if not spans or (len(spans) == 1 and not spans[0].text.strip()):
            continue
        y = TITLEBAR_H + PADDING_Y + (i + 1) * LINE_HEIGHT - 4
        lines_svg.append(svg_text_spans(spans, PADDING_X, y))

    content_block = "\n    ".join(lines_svg)
    title_x = width // 2
    title_y = TITLEBAR_H // 2 + 5

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{width}" height="{height}"
     viewBox="0 0 {width} {height}">

  <!-- Drop shadow -->
  <defs>
    <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">
      <feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#000000" flood-opacity="0.5"/>
    </filter>
  </defs>

  <!-- Window frame -->
  <rect x="0" y="0" width="{width}" height="{height}"
        rx="{CORNER_R}" ry="{CORNER_R}"
        fill="{BG}" filter="url(#shadow)" />

  <!-- Title bar -->
  <rect x="0" y="0" width="{width}" height="{TITLEBAR_H}"
        rx="{CORNER_R}" ry="{CORNER_R}" fill="{TITLEBAR}" />
  <rect x="0" y="{TITLEBAR_H // 2}" width="{width}" height="{TITLEBAR_H // 2}"
        fill="{TITLEBAR}" />

  <!-- Traffic lights -->
  {traffic_lights_svg(20, TITLEBAR_H // 2)}

  <!-- Title text -->
  <text x="{title_x}" y="{title_y}"
        font-family="{SVG_FONT}" font-size="13"
        fill="{TITLE_TEXT_COLOR}" text-anchor="middle">{escape(title)}</text>

  <!-- Terminal content -->
  {content_block}

</svg>
"""


# ===========================================================================
# GIF renderer
# ===========================================================================

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (FONT_BOLD_PATH if bold else FONT_PATH, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(key[0], size)
    return _font_cache[key]


def _gif_height(num_lines: int) -> int:
    return GIF_CONTENT_Y0 + num_lines * LINE_HEIGHT + GIF_BOTTOM_PAD


def _draw_chrome(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """Draw macOS-style title bar with traffic lights."""
    draw.rounded_rectangle(
        [(0, 0), (width - 1, height - 1)],
        radius=GIF_CORNER_RADIUS, fill=BG,
    )
    draw.rounded_rectangle(
        [(0, 0), (width - 1, TITLEBAR_H)],
        radius=GIF_CORNER_RADIUS, fill=TITLEBAR,
    )
    draw.rectangle(
        [(0, TITLEBAR_H - GIF_CORNER_RADIUS), (width - 1, TITLEBAR_H)],
        fill=TITLEBAR,
    )

    for cx, color in [(20, TL_RED), (40, TL_YELLOW), (60, TL_GREEN)]:
        draw.ellipse([(cx - 7, 19 - 7), (cx + 7, 19 + 7)], fill=color)

    title = "miaodx@jj-mailbox: ~"
    title_font = _font(GIF_TITLE_FONT_SIZE)
    bbox = title_font.getbbox(title)
    tw = bbox[2] - bbox[0]
    tx = (width - tw) // 2
    draw.text((tx, 10), title, fill=TITLE_TEXT_COLOR, font=title_font)


def _draw_gif_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
) -> None:
    """Draw colored content lines onto a GIF frame."""
    y = GIF_CONTENT_Y0
    for ln in lines:
        # Replace emojis for GIF rendering
        ln_clean = replace_emojis_for_gif(ln)
        segments = colorize_line(ln_clean)
        x = GIF_LEFT_PAD
        for span in segments:
            draw.text((x, y), span.text, fill=span.color, font=font)
            bbox = font.getbbox(span.text)
            x += bbox[2] - bbox[0]
        y += LINE_HEIGHT


def _render_gif_frame(
    all_lines: list[str],
    visible_count: int,
    total_lines: int,
) -> Image.Image:
    """Render a single GIF frame showing the first *visible_count* lines."""
    height = _gif_height(total_lines)
    img = Image.new("RGB", (GIF_WIDTH, height), BG)
    draw = ImageDraw.Draw(img)
    _draw_chrome(draw, GIF_WIDTH, height)
    _draw_gif_lines(draw, all_lines[:visible_count], _font(GIF_FONT_SIZE))
    return img


def render_gif(groups: list[tuple[str, list[str]]], path: Path) -> None:
    """Build an animated GIF from grouped line sequences.

    *kind* controls timing:
      - "cmd"    : shown alone, CMD_HOLD ms pause
      - "output" : lines appear as a batch
      - "title"  : section header, treated like output
    After each group, GROUP_PAUSE ms. Final frame held FINAL_HOLD ms.
    """
    # Flatten all lines to compute total height
    all_lines: list[str] = []
    for _, lines in groups:
        all_lines.extend(lines)
    total_lines = len(all_lines)

    frames: list[Image.Image] = []
    durations: list[int] = []

    visible = 0
    for gi, (kind, lines) in enumerate(groups):
        visible += len(lines)
        frame = _render_gif_frame(all_lines, visible, total_lines)
        frames.append(frame)
        if gi == len(groups) - 1:
            durations.append(FINAL_HOLD)
        elif kind == "cmd":
            durations.append(CMD_HOLD)
        else:
            durations.append(GROUP_PAUSE)

    if not frames:
        print(f"  WARNING: No frames to render for {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        str(path),
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    size_kb = path.stat().st_size / 1024
    print(f"  wrote {path} ({size_kb:.0f} KB, {len(frames)} frames)")


# ===========================================================================
# Figure builders
# ===========================================================================

def build_test_suite_lines(captured: list[str]) -> list[str]:
    """Prepend command, return lines for the test-suite figure."""
    return ["$ uv run python tests/run_all.py --no-llm", ""] + captured


def build_agent_lines(captured: list[str]) -> list[str]:
    """Prepend command, return lines for the agent-conversation figure."""
    return ["$ uv run python tests/scripted/test.py", ""] + captured


def build_agent_groups(captured: list[str]) -> list[tuple[str, list[str]]]:
    """Split captured agent conversation lines into animation groups."""
    groups: list[tuple[str, list[str]]] = [
        ("cmd", ["$ uv run python tests/scripted/test.py"]),
    ]

    current_kind = "output"
    current_lines: list[str] = []

    for ln in captured:
        stripped = ln.strip()
        if stripped.startswith("Turn "):
            # Start new group for each turn
            if current_lines:
                groups.append((current_kind, current_lines))
            current_kind = "output"
            current_lines = [ln]
        elif stripped.startswith("Assertions:"):
            if current_lines:
                groups.append((current_kind, current_lines))
            current_kind = "output"
            current_lines = [ln]
        elif stripped.startswith("\u2705") or stripped.startswith("[PASS]"):
            if current_lines:
                groups.append((current_kind, current_lines))
            groups.append(("output", [ln]))
            current_lines = []
        elif stripped.startswith("Level "):
            if current_lines:
                groups.append((current_kind, current_lines))
            groups.append(("title", [ln]))
            current_lines = []
        elif not stripped:
            # Blank line: skip for grouping (don't emit empty groups)
            if current_lines:
                current_lines.append(ln)
        else:
            current_lines.append(ln)

    if current_lines:
        groups.append((current_kind, current_lines))

    return groups


def build_mailbox_svg_lines(groups: list[tuple[str, list[str]]]) -> list[str]:
    """Flatten mailbox demo groups into lines for SVG rendering."""
    all_lines: list[str] = []
    for kind, lines in groups:
        all_lines.extend(lines)
        all_lines.append("")  # blank line between groups
    # Remove trailing blank
    while all_lines and not all_lines[-1].strip():
        all_lines.pop()
    return all_lines


# ===========================================================================
# Main orchestrator
# ===========================================================================

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Capturing test suite output...")
    test_lines = capture_test_suite()

    print("Capturing agent conversation output...")
    agent_lines = capture_agent_conversation()

    print("Capturing mailbox demo output...")
    mailbox_groups = capture_mailbox_demo()

    # --- 1. test-suite.svg ---
    print("Rendering test-suite.svg...")
    svg_lines = build_test_suite_lines(test_lines)
    svg_str = render_svg(svg_lines)
    dest = OUTPUT_DIR / "test-suite.svg"
    dest.write_text(svg_str, encoding="utf-8")
    print(f"  wrote {dest}")

    # --- 2. agent-conversation.svg ---
    print("Rendering agent-conversation.svg...")
    agent_svg_lines = build_agent_lines(agent_lines)
    svg_str = render_svg(agent_svg_lines)
    dest = OUTPUT_DIR / "agent-conversation.svg"
    dest.write_text(svg_str, encoding="utf-8")
    print(f"  wrote {dest}")

    # --- 3. agent-conversation.gif ---
    print("Rendering agent-conversation.gif...")
    agent_groups = build_agent_groups(agent_lines)
    render_gif(agent_groups, OUTPUT_DIR / "agent-conversation.gif")

    # --- 4. mailbox-status.svg ---
    print("Rendering mailbox-status.svg...")
    mailbox_svg_lines = build_mailbox_svg_lines(mailbox_groups)
    svg_str = render_svg(mailbox_svg_lines)
    dest = OUTPUT_DIR / "mailbox-status.svg"
    dest.write_text(svg_str, encoding="utf-8")
    print(f"  wrote {dest}")

    # --- 5. mailbox-status.gif ---
    print("Rendering mailbox-status.gif...")
    render_gif(mailbox_groups, OUTPUT_DIR / "mailbox-status.gif")

    print("\nDone. Generated 5 figures in docs/fig/")


if __name__ == "__main__":
    main()
