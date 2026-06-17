#!/usr/bin/env python3
"""
xxdart — Steganography tool: hides ASCII art in binary files.

The art is invisible to casual viewers but becomes readable when the file is
examined with the GNU `xxd` hex-dump utility using a specific combination of
flags.  Those flags are the "viewing key":

    -c N   bytes-per-row  (must equal the art's pixel-row width)
    -s N   skip N leading cover bytes  (must match --start-offset)
    -g N   hex grouping   (relevant for --mode hex)
    -b     binary dump    (show bits instead of hex, for --mode binary)
    -l N   limit output to N bytes

Wrong key → rows wrap incorrectly → art is destroyed.
Right key → hidden message is revealed, one xxd row per pixel row.
"""

import argparse
import os
import random
import subprocess
import sys
import textwrap

# ═══════════════════════════════════════════════════════════════════════════════
#  BITMAP FONT — 5 × 7 pixels per glyph
#
#  Each glyph is a list of GLYPH_H (7) strings, each exactly GLYPH_W (5) chars.
#  '#' = lit pixel   ' ' = dark pixel
#
#  A-Z uppercase are defined explicitly.  Lowercase falls back to uppercase.
# ═══════════════════════════════════════════════════════════════════════════════
GLYPH_W: int = 5   # pixel width of one character cell
GLYPH_H: int = 7   # pixel height of one character cell
SPACING: int = 1   # dark-pixel columns between glyphs  (horizontal layout)
VSPACING: int = 1  # blank rows between glyphs           (vertical layout)

# xxd hard-limits -c to 256 bytes per row.  Horizontal layout needs
# cols = N*GLYPH_W + (N-1)*SPACING which grows with message length.
# Vertical layout always uses cols = GLYPH_W (5), so it never hits the limit.
XXD_MAX_COLS: int = 256

FONT: dict[str, list[str]] = {
    # ── printable ASCII, in codepoint order ──────────────────────────────────
    ' ':  ["     "] * 7,
    '!':  ["  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "     ", "  #  "],
    '"':  [" # # ", " # # ", "     ", "     ", "     ", "     ", "     "],
    '#':  [" # # ", " # # ", "#####", " # # ", "#####", " # # ", " # # "],
    '$':  [" ### ", "# # #", "# #  ", " ### ", "  # #", "# # #", " ### "],
    '%':  ["#   #", "#  # ", "   # ", "  #  ", " #   ", " #  #", "#   #"],
    '&':  [" ##  ", "#  # ", "#  # ", " ##  ", "# # #", "#  # ", " ## #"],
    "'":  ["  #  ", "  #  ", "     ", "     ", "     ", "     ", "     "],
    '(':  ["  ## ", " #   ", "#    ", "#    ", "#    ", " #   ", "  ## "],
    ')':  [" ##  ", "   # ", "    #", "    #", "    #", "   # ", " ##  "],
    '*':  ["     ", " # # ", "  #  ", "#####", "  #  ", " # # ", "     "],
    '+':  ["     ", "  #  ", "  #  ", "#####", "  #  ", "  #  ", "     "],
    ',':  ["     ", "     ", "     ", "     ", "  #  ", "  #  ", " #   "],
    '-':  ["     ", "     ", "     ", "#####", "     ", "     ", "     "],
    '.':  ["     ", "     ", "     ", "     ", "     ", "     ", "  #  "],
    '/':  ["    #", "   # ", "   # ", "  #  ", " #   ", " #   ", "#    "],
    # ── digits ───────────────────────────────────────────────────────────────
    '0':  [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    '1':  ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"],
    '2':  [" ### ", "#   #", "    #", "  ## ", " #   ", "#    ", "#####"],
    '3':  ["#####", "    #", "    #", " ### ", "    #", "    #", "#####"],
    '4':  ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    '5':  ["#####", "#    ", "#    ", "#### ", "    #", "    #", "#### "],
    '6':  [" ### ", "#    ", "#    ", "#### ", "#   #", "#   #", " ### "],
    '7':  ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    '8':  [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    '9':  [" ### ", "#   #", "#   #", " ####", "    #", "    #", " ### "],
    # ── punctuation (continued) ───────────────────────────────────────────────
    ':':  ["     ", "  #  ", "  #  ", "     ", "  #  ", "  #  ", "     "],
    ';':  ["     ", "  #  ", "  #  ", "     ", "  #  ", "  #  ", " #   "],
    '<':  ["   # ", "  #  ", " #   ", "#    ", " #   ", "  #  ", "   # "],
    '=':  ["     ", "     ", "#####", "     ", "#####", "     ", "     "],
    '>':  [" #   ", "  #  ", "   # ", "    #", "   # ", "  #  ", " #   "],
    '?':  [" ### ", "#   #", "    #", "  ## ", "  #  ", "     ", "  #  "],
    '@':  [" ### ", "#   #", "#  ##", "# # #", "# ###", "#    ", " ### "],
    # ── uppercase A-Z ─────────────────────────────────────────────────────────
    'A':  [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    'B':  ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    'C':  [" ####", "#    ", "#    ", "#    ", "#    ", "#    ", " ####"],
    'D':  ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    'E':  ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    'F':  ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    'G':  [" ####", "#    ", "#    ", "#  ##", "#   #", "#   #", " ####"],
    'H':  ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    'I':  ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"],
    'J':  ["#####", "    #", "    #", "    #", "    #", "#   #", " ### "],
    'K':  ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    'L':  ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    'M':  ["#   #", "## ##", "# # #", "#   #", "#   #", "#   #", "#   #"],
    'N':  ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
    'O':  [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    'P':  ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    'Q':  [" ### ", "#   #", "#   #", "#   #", "# # #", "#  ##", " ####"],
    'R':  ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    'S':  [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
    'T':  ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    'U':  ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    'V':  ["#   #", "#   #", "#   #", "#   #", " # # ", " # # ", "  #  "],
    'W':  ["#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"],
    'X':  ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    'Y':  ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    'Z':  ["#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"],
    # ── remaining printable ASCII ─────────────────────────────────────────────
    '[':  [" ### ", " #   ", " #   ", " #   ", " #   ", " #   ", " ### "],
    ']':  [" ### ", "   # ", "   # ", "   # ", "   # ", "   # ", " ### "],
    '^':  ["  #  ", " # # ", "#   #", "     ", "     ", "     ", "     "],
    '_':  ["     ", "     ", "     ", "     ", "     ", "     ", "#####"],
    '`':  [" #   ", "  #  ", "     ", "     ", "     ", "     ", "     "],
    '{':  ["   ##", "  #  ", "  #  ", "##   ", "  #  ", "  #  ", "   ##"],
    '|':  ["  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    '}':  ["##   ", "  #  ", "  #  ", "   ##", "  #  ", "  #  ", "##   "],
    '~':  ["     ", " ##  ", "#  ##", "     ", "     ", "     ", "     "],
}

# Lowercase letters fall back to their uppercase equivalents.
for _ch in "abcdefghijklmnopqrstuvwxyz":
    if _ch not in FONT:
        FONT[_ch] = FONT[_ch.upper()]


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPACT FONT — 3 × 7 pixels per glyph  (used by --mode binary)
#
#  Binary mode prints 8-character groups per byte.  A 5-wide glyph produces
#  5 groups per row (e.g. "11111111 00000000 00000000 00000000 11111111").
#  A 3-wide glyph reduces that to 3 groups, which is easier to read and fits
#  comfortably in a standard 80-column terminal.
#
#  Each glyph row is exactly GLYPH_W_3 (3) characters: '#' = lit, ' ' = dark.
# ═══════════════════════════════════════════════════════════════════════════════
GLYPH_W_3: int = 3

FONT_3: dict[str, list[str]] = {
    ' ':  ["   "] * 7,
    '!':  [" # ", " # ", " # ", " # ", " # ", "   ", " # "],
    '"':  ["# #", "# #", "   ", "   ", "   ", "   ", "   "],
    '#':  ["# #", "###", "# #", "###", "# #", "# #", "   "],
    '$':  [" # ", "###", "#  ", "###", "  #", "###", " # "],
    '%':  ["# #", "# #", "  #", " # ", "#  ", "# #", "# #"],
    '&':  [" # ", "# #", " # ", "## ", "# #", "# #", " ##"],
    "'":  [" # ", " # ", "#  ", "   ", "   ", "   ", "   "],
    '(':  [" # ", "#  ", "#  ", "#  ", "#  ", "#  ", " # "],
    ')':  [" # ", "  #", "  #", "  #", "  #", "  #", " # "],
    '*':  ["   ", "# #", " # ", "###", " # ", "# #", "   "],
    '+':  ["   ", " # ", " # ", "###", " # ", " # ", "   "],
    ',':  ["   ", "   ", "   ", "   ", " # ", " # ", "#  "],
    '-':  ["   ", "   ", "   ", "###", "   ", "   ", "   "],
    '.':  ["   ", "   ", "   ", "   ", "   ", "   ", " # "],
    '/':  ["  #", "  #", " # ", " # ", "#  ", "#  ", "#  "],
    '0':  ["###", "# #", "# #", "# #", "# #", "# #", "###"],
    '1':  [" # ", "## ", " # ", " # ", " # ", " # ", "###"],
    '2':  ["## ", "  #", "  #", " ##", "#  ", "#  ", "###"],
    '3':  ["###", "  #", "  #", " ##", "  #", "  #", "###"],
    '4':  ["# #", "# #", "# #", "###", "  #", "  #", "  #"],
    '5':  ["###", "#  ", "#  ", "## ", "  #", "  #", "###"],
    '6':  ["###", "#  ", "#  ", "## ", "# #", "# #", "###"],
    '7':  ["###", "  #", "  #", " # ", " # ", " # ", " # "],
    '8':  ["###", "# #", "# #", "###", "# #", "# #", "###"],
    '9':  ["###", "# #", "# #", "###", "  #", "  #", "###"],
    ':':  ["   ", " # ", " # ", "   ", " # ", " # ", "   "],
    ';':  ["   ", " # ", " # ", "   ", " # ", " # ", "#  "],
    '<':  ["  #", " # ", "#  ", "#  ", "#  ", " # ", "  #"],
    '=':  ["   ", "###", "   ", "###", "   ", "   ", "   "],
    '>':  ["#  ", " # ", "  #", "  #", "  #", " # ", "#  "],
    '?':  ["## ", "  #", " ##", " # ", " # ", "   ", " # "],
    '@':  ["###", "#  ", "# #", "# #", "# #", "#  ", "###"],
    'A':  [" # ", "# #", "# #", "###", "# #", "# #", "# #"],
    'B':  ["## ", "# #", "# #", "## ", "# #", "# #", "## "],
    'C':  ["###", "#  ", "#  ", "#  ", "#  ", "#  ", "###"],
    'D':  ["## ", "# #", "# #", "# #", "# #", "# #", "## "],
    'E':  ["###", "#  ", "#  ", "## ", "#  ", "#  ", "###"],
    'F':  ["###", "#  ", "#  ", "## ", "#  ", "#  ", "#  "],
    'G':  ["###", "#  ", "#  ", "# #", "# #", "# #", "###"],
    'H':  ["# #", "# #", "# #", "###", "# #", "# #", "# #"],
    'I':  ["###", " # ", " # ", " # ", " # ", " # ", "###"],
    'J':  [" ##", "  #", "  #", "  #", "  #", "# #", "## "],
    'K':  ["# #", "# #", "## ", "#  ", "## ", "# #", "# #"],
    'L':  ["#  ", "#  ", "#  ", "#  ", "#  ", "#  ", "###"],
    'M':  ["# #", "###", "# #", "# #", "# #", "# #", "# #"],
    'N':  ["# #", "## ", "# #", "# #", "# #", " ##", "# #"],
    'O':  ["###", "# #", "# #", "# #", "# #", "# #", "###"],
    'P':  ["## ", "# #", "# #", "## ", "#  ", "#  ", "#  "],
    'Q':  ["###", "# #", "# #", "# #", "# #", " ##", "###"],
    'R':  ["## ", "# #", "# #", "## ", "# #", "# #", "# #"],
    'S':  ["###", "#  ", "#  ", "###", "  #", "  #", "###"],
    'T':  ["###", " # ", " # ", " # ", " # ", " # ", " # "],
    'U':  ["# #", "# #", "# #", "# #", "# #", "# #", "###"],
    'V':  ["# #", "# #", "# #", "# #", "# #", " # ", " # "],
    'W':  ["# #", "# #", "# #", "###", " # ", "# #", "# #"],
    'X':  ["# #", "# #", " # ", " # ", " # ", "# #", "# #"],
    'Y':  ["# #", "# #", "###", " # ", " # ", " # ", " # "],
    'Z':  ["###", "  #", " # ", " # ", "#  ", "#  ", "###"],
    '[':  ["## ", "#  ", "#  ", "#  ", "#  ", "#  ", "## "],
    ']':  [" ##", "  #", "  #", "  #", "  #", "  #", " ##"],
    '^':  [" # ", "# #", "   ", "   ", "   ", "   ", "   "],
    '_':  ["   ", "   ", "   ", "   ", "   ", "   ", "###"],
    '`':  ["#  ", " # ", "   ", "   ", "   ", "   ", "   "],
    '{':  [" ##", " # ", " # ", "#  ", " # ", " # ", " ##"],
    '|':  [" # ", " # ", " # ", " # ", " # ", " # ", " # "],
    '}':  ["## ", " # ", " # ", "  #", " # ", " # ", "## "],
    '~':  ["   ", "## ", "  #", "  #", "   ", "   ", "   "],
}

for _ch in "abcdefghijklmnopqrstuvwxyz":
    if _ch not in FONT_3:
        FONT_3[_ch] = FONT_3[_ch.upper()]


# ═══════════════════════════════════════════════════════════════════════════════
#  RENDERING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_glyph(char: str, font: dict | None = None) -> list[str]:
    """Return the bitmap rows for *char* from *font* (defaults to FONT).

    Falls back to uppercase, then to '?' if both are missing.
    """
    f = font if font is not None else FONT
    fallback_w = len(next(iter(f.values()))[0])  # width from first entry
    return f.get(char) or f.get(char.upper()) or f.get('?', ["#" * fallback_w] * GLYPH_H)


def pack_glyph_row(row_str: str) -> int:
    """Pack a glyph pixel row into a single byte, bits left-aligned.

    '#' maps to 1, ' ' maps to 0.  The first pixel occupies bit 7 (MSB).
    Up to 8 pixels fit; unused low bits are zero.

    Examples (5-wide glyph):
      '#...#' → 10001000 = 0x88
      '#####' → 11111000 = 0xF8
      '  #  ' → 00100000 = 0x20
    """
    result = 0
    for i, ch in enumerate(row_str[:8]):
        if ch == '#':
            result |= (1 << (7 - i))
    return result


def message_to_bitmap(
    message: str,
    on_byte: int,
    off_byte: int,
    cols_per_row: int | None,
    layout: str = "vertical",
    font: dict | None = None,
    glyph_w: int = GLYPH_W,
    bytes_per_pixel: int = 1,
    packed: bool = False,
) -> tuple[bytes, int, int]:
    """Convert *message* to a flat byte string representing a 2-D pixel art bitmap.

    Parameters
    ----------
    font            : glyph dict to use; None → FONT (5-wide).
    glyph_w         : pixel width of one glyph cell (must match *font*).
    bytes_per_pixel : how many bytes to write per pixel.  1 = one byte per
                      pixel (ascii/binary modes).  2 = two identical bytes per
                      pixel (hex mode, so xxd -g 2 shows "8888" vs "1111").
    packed          : if True, each glyph row is bit-packed into a single byte
                      (left-aligned, MSB = first pixel).  cols is always 1.
                      Used by binary-packed mode: xxd -b -c 1 shows exactly
                      one row of 8 binary digits per line.  on_byte/off_byte
                      are ignored when packed=True.

    Layout math — VERTICAL (default)
    ---------------------------------
    Normal:  cols = glyph_w * bytes_per_pixel   (fixed; always fits ≤ 256)
    Packed:  cols = 1                            (1 byte per glyph row)
    rows = N * GLYPH_H + (N-1) * VSPACING

    Layout math — HORIZONTAL (opt-in, --layout horizontal)
    -------------------------------------------------------
      cols  (-c) = (N * glyph_w + (N-1) * SPACING) * bytes_per_pixel
      rows       = GLYPH_H = 7
    Packed mode is not supported in horizontal layout.

    Returns
    -------
    (flat_bytes, effective_cols, total_rows)
    """
    if packed and layout != "vertical":
        raise ValueError("Packed binary encoding is only supported with --layout vertical.")

    active_font = font if font is not None else FONT

    # ── collect glyphs, warn about unsupported chars ──────────────────────────
    glyphs: list[list[str]] = []
    skipped: list[str] = []
    for ch in message:
        if ch in active_font or ch.upper() in active_font:
            glyphs.append(get_glyph(ch, active_font))
        else:
            skipped.append(repr(ch))

    if skipped:
        print(
            f"WARNING: skipping unsupported characters: {', '.join(skipped)}",
            file=sys.stderr,
        )

    if not glyphs:
        raise ValueError("No renderable characters in message after filtering.")

    result = bytearray()
    pixel_stride = glyph_w * bytes_per_pixel   # bytes consumed by one glyph row

    # ══════════════════════════════════════════════════════════════════════════
    if layout == "vertical":

        if packed:
            # ── packed binary: one byte per glyph row, bits = pixels ──────────
            # col width is always 1; cols_per_row is ignored.
            effective_cols: int = 1

            for g_idx, glyph in enumerate(glyphs):
                for row_idx in range(GLYPH_H):
                    result.append(pack_glyph_row(glyph[row_idx]))
                if g_idx < len(glyphs) - 1:
                    result.append(0x00)  # blank separator row

        else:
            # ── normal blocks: one on/off byte per pixel ───────────────────────
            # Each glyph occupies GLYPH_H rows; each row is pixel_stride bytes.
            # One blank row of off_bytes is inserted between consecutive glyphs.

            if cols_per_row is not None and cols_per_row < pixel_stride:
                raise ValueError(
                    f"--cols-per-row {cols_per_row} is too narrow for vertical layout "
                    f"(minimum {pixel_stride} bytes/row)."
                )
            effective_cols = cols_per_row if cols_per_row is not None else pixel_stride
            right_pad: int = effective_cols - pixel_stride

            for g_idx, glyph in enumerate(glyphs):
                for row_idx in range(GLYPH_H):
                    row_bytes = bytearray()
                    for px in glyph[row_idx]:
                        b = on_byte if px == '#' else off_byte
                        for _ in range(bytes_per_pixel):
                            row_bytes.append(b)
                    row_bytes.extend([off_byte] * right_pad)
                    assert len(row_bytes) == effective_cols
                    result.extend(row_bytes)

                if g_idx < len(glyphs) - 1:
                    result.extend([off_byte] * effective_cols)

        total_rows = len(glyphs) * GLYPH_H + (len(glyphs) - 1) * VSPACING

    # ══════════════════════════════════════════════════════════════════════════
    else:  # layout == "horizontal"
        # All glyphs placed side by side; cols grows with message length.

        natural_width = (len(glyphs) * glyph_w + (len(glyphs) - 1) * SPACING) * bytes_per_pixel

        if natural_width > XXD_MAX_COLS:
            raise ValueError(
                f"Horizontal layout requires -c {natural_width}, which exceeds "
                f"xxd's maximum of {XXD_MAX_COLS} bytes/row.\n"
                f"  This message fits up to ~{(XXD_MAX_COLS // bytes_per_pixel + SPACING) // (glyph_w + SPACING)} "
                f"characters in horizontal mode.\n"
                f"  Use --layout vertical (the default) for longer messages."
            )

        if cols_per_row is not None and cols_per_row < natural_width:
            raise ValueError(
                f"--cols-per-row {cols_per_row} is too narrow for a {len(glyphs)}-glyph "
                f"horizontal message (minimum {natural_width} bytes/row)."
            )

        effective_cols = cols_per_row if cols_per_row is not None else natural_width
        right_pad = effective_cols - natural_width

        for row_idx in range(GLYPH_H):
            row_bytes = bytearray()
            for g_idx, glyph in enumerate(glyphs):
                for px in glyph[row_idx]:
                    b = on_byte if px == '#' else off_byte
                    for _ in range(bytes_per_pixel):
                        row_bytes.append(b)
                if g_idx < len(glyphs) - 1:
                    for _ in range(SPACING * bytes_per_pixel):
                        row_bytes.append(off_byte)
            row_bytes.extend([off_byte] * right_pad)
            assert len(row_bytes) == effective_cols
            result.extend(row_bytes)

        total_rows = GLYPH_H

    return bytes(result), effective_cols, total_rows


def make_noise_bytes(n: int, noise_type: str) -> bytes:
    """Return *n* cover bytes prepended before the art."""
    if noise_type == "random":
        return bytes(random.randint(0, 255) for _ in range(n))
    return bytes(n)  # zeros


# ═══════════════════════════════════════════════════════════════════════════════
#  xxd COMMAND CONSTRUCTION + GREP COLORISER
# ═══════════════════════════════════════════════════════════════════════════════

def build_xxd_cmd(
    outfile: str,
    cols: int,
    start_offset: int,
    group: int,
    limit: int | None,
    mode: str,
) -> list[str]:
    """Return the xxd argv list that reveals the hidden art.

    Flags used as the "viewing key":
      -c cols         → bytes per row must equal art pixel-row width
      -s start_offset → skip cover bytes
      -g group        → hex grouping (matters for hex/binary mode art)
      -b              → binary dump (for binary mode)
      -l limit        → optional: trim output to exactly the art section
    """
    cmd = ["xxd"]

    # -b must come before other flags for some xxd versions.
    if mode == "binary":
        cmd.append("-b")

    cmd += ["-c", str(cols)]

    if start_offset > 0:
        cmd += ["-s", str(start_offset)]

    # Always emit -g so the receiver uses the exact expected grouping.
    cmd += ["-g", str(group)]

    if limit is not None:
        cmd += ["-l", str(limit)]

    cmd.append(outfile)
    return cmd


def build_grep_cmd(mode: str, on_byte: int) -> list[str] | None:
    """Return a grep argv list that colour-highlights the art in xxd output.

    Highlights the lit-pixel marker so the art pops visually:
      ascii  → the on_byte character itself (e.g. '#' for 0x23)
      hex    → the two-digit hex group that represents a lit pixel
               (e.g. '88' for on_byte=0x88, since each pixel writes two
               identical bytes and xxd -g 2 renders them as '8888')
      binary → '11'  (two consecutive set-bits; avoids false highlights on
               single '1' digits that appear in the hex address column)

    The pattern ``<token>\\|$`` uses GNU BRE alternation: it matches either the
    token OR the end of every line, so the ANSI reset code is emitted at each
    line end and colours never bleed between rows.

    Returns None if a colour command cannot be constructed (non-printable
    on_byte in ascii mode).
    """
    if mode == "binary":
        # '11' matches set-bit pairs inside '11111111' blocks without hitting
        # single digits in the offset column (e.g. '00000001').
        pattern = "11\\|$"

    elif mode == "hex":
        # on_byte is written twice per pixel (bytes_per_pixel=2), so xxd -g 2
        # shows the digit pair repeated: 0x88 → '8888'.  Matching the two-digit
        # repetition avoids false highlights on single-digit address characters.
        digit = f"{on_byte:02x}"[0]
        pattern = f"{digit}{digit}\\|$"

    else:  # ascii
        if not (0x20 <= on_byte <= 0x7E):
            return None
        char = chr(on_byte)
        # Escape BRE meta-characters that are special at pattern start.
        if char in r'\.^$*[]':
            char = '\\' + char
        pattern = f"{char}\\|$"

    return ["grep", "--color=always", pattern]


def _grep_display(grep_cmd: list[str] | None) -> str | None:
    """Return the copy-pasteable shell snippet for the grep pipe.

    Uses ``--color`` (auto) instead of ``--color=always`` for the display
    string, and wraps the pattern in single quotes.
    """
    if grep_cmd is None:
        return None
    parts = list(grep_cmd)
    # Replace --color=always with --color for the human-readable display.
    parts = [p.replace("--color=always", "--color") for p in parts]
    # Single-quote the pattern (last element) for safe shell copy-paste.
    parts[-1] = f"'{parts[-1]}'"
    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
#  VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def _xxd_ascii_repr(byte: int) -> str:
    """Return how xxd renders *byte* in its ASCII column (printable or '.')."""
    return chr(byte) if 0x20 <= byte <= 0x7E else "."


def _extract_ascii_col(line: str) -> str:
    """Return the ASCII column from a single xxd output line.

    xxd format:  ``XXXXXXXX: <hex>  <ascii>\\n``
    The hex and ASCII sections are separated by exactly two spaces.
    """
    # Split on double-space; last segment is the ASCII column.
    parts = line.rstrip("\n").split("  ")
    return parts[-1] if len(parts) >= 2 else ""


def _extract_data_col(line: str) -> str:
    """Return the hex/binary data column from an xxd output line, spaces removed.

    Works for both hex mode (``ab cd ef``) and binary mode
    (``01000001 01000010``).  Grouping spaces are stripped so the caller
    gets a continuous string of hex digits or binary digits.
    """
    colon = line.find(": ")
    if colon < 0:
        return ""
    rest = line[colon + 2:]
    data_part = rest.split("  ")[0]
    return data_part.replace(" ", "")  # strip -g grouping spaces


def verify_and_display(
    outfile: str,
    art_bytes: bytes,
    start_offset: int,
    cols: int,
    total_rows: int,
    mode: str,
    on_byte: int,
    off_byte: int,
    xxd_cmd: list[str],
    grep_cmd: list[str] | None = None,
) -> bool:
    """Run xxd, display its output, and assert the art rows are present.

    Verification strategy
    ---------------------
    1. Read the written file and compare bytes at [start_offset : start_offset
       + len(art_bytes)] against the expected bitmap.  This is the ground-truth
       check.
    2. Run xxd with the computed flags and capture stdout.
    3. Parse each output line and compare the relevant column (ASCII or hex)
       against the expected pixel row.
    4. Print "VERIFIED OK" on success or a clear error on failure.
    """
    # ── byte-level check ──────────────────────────────────────────────────────
    with open(outfile, "rb") as fh:
        written = fh.read()
    actual_art = written[start_offset : start_offset + len(art_bytes)]
    if actual_art != art_bytes:
        print("VERIFICATION FAILED: written bytes differ from expected bitmap.", file=sys.stderr)
        return False

    # ── run xxd ──────────────────────────────────────────────────────────────
    try:
        result = subprocess.run(xxd_cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        print(
            "\nERROR: 'xxd' is not installed or not in PATH.\n"
            "  The file was written and byte-verified successfully.\n"
            "  Install xxd (e.g. `sudo apt install xxd` or `brew install vim`) and run:\n"
            f"    {' '.join(xxd_cmd)}",
            file=sys.stderr,
        )
        # Byte check already passed — report partial success.
        print("\nBYTE-VERIFIED OK  (xxd display skipped — xxd not found)")
        return True
    except subprocess.TimeoutExpired:
        print("ERROR: xxd timed out.", file=sys.stderr)
        return False

    if result.returncode != 0:
        print(f"ERROR: xxd exited {result.returncode}: {result.stderr}", file=sys.stderr)
        return False

    # ── build expected column content for each art row ────────────────────────
    # Reconstruct per-row byte sequences from art_bytes.
    # For ascii mode  → expected content is the ASCII column characters.
    # For hex mode    → expected content is contiguous hex digits  (spaces stripped).
    # For binary mode → expected content is contiguous binary digits (spaces stripped).
    expected_rows: list[str] = []
    for row_idx in range(total_rows):
        row_bytes = art_bytes[row_idx * cols : (row_idx + 1) * cols]
        if mode == "ascii":
            expected_rows.append("".join(_xxd_ascii_repr(b) for b in row_bytes))
        elif mode == "hex":
            expected_rows.append("".join(f"{b:02x}" for b in row_bytes))
        else:  # binary
            expected_rows.append("".join(f"{b:08b}" for b in row_bytes))

    # ── parse xxd output lines ────────────────────────────────────────────────
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    mismatches: list[str] = []

    for art_row_idx, expected in enumerate(expected_rows):
        if art_row_idx >= len(lines):
            mismatches.append(f"  row {art_row_idx}: xxd output has fewer lines than expected")
            continue
        line = lines[art_row_idx]
        if mode == "ascii":
            actual_col = _extract_ascii_col(line)
        else:  # hex or binary — both use the data column
            actual_col = _extract_data_col(line)

        if actual_col != expected:
            mismatches.append(
                f"  art row {art_row_idx}: expected {repr(expected)}\n"
                f"                  got      {repr(actual_col)}"
            )

    # ── display xxd output (colourised if grep is available) ─────────────────
    if grep_cmd is not None:
        try:
            subprocess.run(
                grep_cmd,
                input=result.stdout,
                text=True,
            )
        except FileNotFoundError:
            # grep not found — fall back to plain output
            print(result.stdout)
    else:
        print(result.stdout)

    if mismatches:
        print("VERIFICATION FAILED — column mismatches:", file=sys.stderr)
        for m in mismatches:
            print(m, file=sys.stderr)
        return False

    print("VERIFIED OK")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
#  ENCODE COMMAND
# ═══════════════════════════════════════════════════════════════════════════════

def encode(args: argparse.Namespace) -> None:
    """Encode the secret message and write the output binary file."""

    # ── validate arguments ────────────────────────────────────────────────────

    if args.start_offset < 0:
        print("ERROR: --start-offset must be >= 0.", file=sys.stderr)
        sys.exit(1)

    if args.cols_per_row is not None and args.cols_per_row <= 0:
        print("ERROR: --cols-per-row must be a positive integer.", file=sys.stderr)
        sys.exit(1)

    if args.group is not None and args.group <= 0:
        print("ERROR: --group must be a positive integer.", file=sys.stderr)
        sys.exit(1)

    if args.limit is not None and args.limit <= 0:
        print("ERROR: --limit must be a positive integer.", file=sys.stderr)
        sys.exit(1)

    if args.on_byte is not None and not (0 <= args.on_byte <= 255):
        print(f"ERROR: --on-byte value {args.on_byte} is out of range (0-255).", file=sys.stderr)
        sys.exit(1)

    if args.off_byte is not None and not (0 <= args.off_byte <= 255):
        print(f"ERROR: --off-byte value {args.off_byte} is out of range (0-255).", file=sys.stderr)
        sys.exit(1)

    if args.binary_style == "packed" and args.layout == "horizontal":
        print("ERROR: --binary-style packed requires --layout vertical.", file=sys.stderr)
        sys.exit(1)

    # ── handle --art-char (ascii mode convenience option) ─────────────────────
    if args.art_char is not None:
        if args.mode != "ascii":
            print(
                "WARNING: --art-char is only meaningful in ascii mode; ignoring.",
                file=sys.stderr,
            )
        elif args.on_byte is not None:
            print(
                "ERROR: Use either --art-char or --on-byte, not both.",
                file=sys.stderr,
            )
            sys.exit(1)
        elif len(args.art_char) != 1:
            print(
                "ERROR: --art-char must be exactly one character.",
                file=sys.stderr,
            )
            sys.exit(1)
        elif args.art_char == '.':
            print(
                "ERROR: '.' as the art character? Seriously?\n"
                "  '.' is already the background pixel — your art would be completely\n"
                "  invisible, a masterpiece of nothing. Try '#', '@', '*', or literally\n"
                "  any other character. Go on, be bold.",
                file=sys.stderr,
            )
            sys.exit(1)
        elif not (0x20 <= ord(args.art_char) <= 0x7E):
            print(
                "ERROR: --art-char must be a printable ASCII character (0x20-0x7E).",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            args.on_byte = ord(args.art_char)

    # ── resolve byte values, grouping, and encoding per mode ──────────────────
    #
    # Mode defaults:
    #   ascii        : on=0x23 '#'  off=0x2E '.'  group=2, bpp=1
    #                    Art appears in xxd's ASCII column.
    #   hex          : on=0x88      off=0x11      group=2, bpp=2
    #                    Each pixel → 2 identical bytes; xxd -g 2 shows "8888"
    #                    (dense figure-eight) vs "1111" (thin stroke).
    #   binary/blocks: on=0xFF      off=0x00      group=1, bpp=1
    #                    3-wide compact font; each row shows 3 binary groups.
    #   binary/packed: bit-packs each glyph row into 1 byte; xxd -b -c 1 shows
    #                    exactly 1 group (8 bits) per line.  The bit pattern IS
    #                    the pixel row.  on/off bytes are unused.
    #
    MODE_DEFAULTS = {
        "ascii":  {"on": 0x23, "off": 0x2E, "group": 2},
        "hex":    {"on": 0x88, "off": 0x11, "group": 2},
        "binary": {"on": 0xFF, "off": 0x00, "group": 1},
    }
    defaults = MODE_DEFAULTS[args.mode]
    on_byte  = args.on_byte  if args.on_byte  is not None else defaults["on"]
    off_byte = args.off_byte if args.off_byte is not None else defaults["off"]
    group    = args.group    if args.group    is not None else defaults["group"]

    if on_byte == off_byte:
        print(
            f"ERROR: --on-byte and --off-byte are both 0x{on_byte:02x}.\n"
            "  Lit and dark pixels would be identical — the art would be completely\n"
            "  invisible. Choose different values for each.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Determine encoding variant for binary mode
    binary_packed = (args.mode == "binary" and args.binary_style == "packed")

    if binary_packed:
        # Packed: 5-wide FONT, 1 byte per glyph row (bit-packed), cols=1
        active_font, active_glyph_w, bytes_per_pixel = FONT, GLYPH_W, 1
    elif args.mode == "binary":
        # Blocks: 3-wide FONT_3, 0xFF/0x00 per pixel, cols=3
        active_font, active_glyph_w, bytes_per_pixel = FONT_3, GLYPH_W_3, 1
    elif args.mode == "hex":
        # 2 bytes per pixel so xxd -g 2 renders "8888"/"1111"
        active_font, active_glyph_w, bytes_per_pixel = FONT, GLYPH_W, 2
    else:  # ascii
        active_font, active_glyph_w, bytes_per_pixel = FONT, GLYPH_W, 1

    # ── render message to bitmap bytes ────────────────────────────────────────
    try:
        art_bytes, cols, total_rows = message_to_bitmap(
            args.message, on_byte, off_byte, args.cols_per_row, args.layout,
            font=active_font, glyph_w=active_glyph_w, bytes_per_pixel=bytes_per_pixel,
            packed=binary_packed,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    art_size = len(art_bytes)  # == total_rows * cols

    # ── generate cover bytes ──────────────────────────────────────────────────
    noise = make_noise_bytes(args.start_offset, args.noise)

    # ── assemble file content ─────────────────────────────────────────────────
    # Layout: [start_offset cover bytes] [GLYPH_H * cols art bytes]
    file_bytes = noise + art_bytes

    # ── write file ────────────────────────────────────────────────────────────
    outfile = args.output
    parent_dir = os.path.dirname(os.path.abspath(outfile))
    os.makedirs(parent_dir, exist_ok=True)

    try:
        with open(outfile, "wb") as fh:
            fh.write(file_bytes)
    except OSError as exc:
        print(f"ERROR: Could not write {outfile!r}: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── compute xxd limit ─────────────────────────────────────────────────────
    # With -s start_offset, xxd already skips the cover bytes, so -l is just the
    # art size.  User may override with --limit.
    limit = args.limit if args.limit is not None else art_size

    # ── build the viewing-key command and optional colour pipe ─────────────────
    xxd_cmd  = build_xxd_cmd(outfile, cols, args.start_offset, group, limit, args.mode)
    grep_cmd = build_grep_cmd(args.mode, on_byte)
    viewing_key  = " ".join(xxd_cmd)
    grep_display = _grep_display(grep_cmd)
    color_key    = f"{viewing_key} | {grep_display}" if grep_display else None

    # ── print summary ─────────────────────────────────────────────────────────
    mode_label = args.mode if not binary_packed else "binary/packed"
    print(f"Wrote {len(file_bytes)} bytes → {outfile}")
    print(f"  Message  : {args.message!r}")
    print(f"  Mode     : {mode_label}")
    if binary_packed:
        print(f"  Encoding : bit-packed  (each pixel row → 1 byte, bit7=left pixel)")
    else:
        on_repr  = repr(chr(on_byte))  if 0x20 <= on_byte  <= 0x7E else "(non-printable)"
        off_repr = repr(chr(off_byte)) if 0x20 <= off_byte <= 0x7E else "(non-printable)"
        print(f"  On-byte  : 0x{on_byte:02x}  (ascii {on_repr}, hex \"{on_byte:02x}\")")
        print(f"  Off-byte : 0x{off_byte:02x}  (ascii {off_repr}, hex \"{off_byte:02x}\")")
    print(f"  Layout   : {args.layout}")
    print(f"  Art size : {total_rows} rows x {cols} cols = {art_size} bytes")
    print(f"  Cover    : {args.start_offset} bytes ({args.noise})")
    print()
    print("═" * 60)
    print("  VIEWING KEY  (share this command with the receiver)")
    print("═" * 60)
    print(f"  {viewing_key}")
    if color_key:
        print(f"\n  With colour highlighting:")
        print(f"  {color_key}")
    print("═" * 60)
    print()

    # Flush stdout before running subprocess so summary appears before xxd output.
    sys.stdout.flush()

    # ── self-verification ─────────────────────────────────────────────────────
    ok = verify_and_display(
        outfile, art_bytes, args.start_offset, cols, total_rows,
        args.mode, on_byte, off_byte, xxd_cmd, grep_cmd,
    )
    if not ok:
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="xxdart",
        description=textwrap.dedent("""\
            xxdart — Hide ASCII art inside a binary file, revealed only with the
            right GNU xxd flags (the "viewing key").

            The message is rendered as a bitmap font and written as raw bytes.
            It is invisible under normal inspection.  The correct xxd flags snap
            the byte rows into alignment and the art appears instantly.  A single
            wrong flag destroys the picture.

            After encoding, the tool runs xxd automatically and pipes the output
            through grep --color so the art is highlighted immediately.

            Subcommands
            -----------
              encode    Render a message and write it to a binary file.
                        (The only subcommand for now — see: xxdart encode --help)

            Quick examples
            --------------
              # ASCII mode — art in the rightmost column, default '#' ink:
                python xxdart.py encode "HELLO" -o secret.bin
                Colourised view:
                  xxd -c 5 -g 2 -l 35 secret.bin | grep --color '#\\|$'

              # Custom ink character:
                python xxdart.py encode "HELLO" -o secret.bin --art-char '@'
                  xxd -c 5 -g 2 -l 35 secret.bin | grep --color '@\\|$'

              # Hex mode — art in the hex column as '8888'/'1111' groups:
                python xxdart.py encode "KEY" -o key.bin --mode hex
                  xxd -c 10 -g 2 -l 161 key.bin | grep --color '88\\|$'

              # Binary blocks — 3 binary groups per row (3-wide compact font):
                python xxdart.py encode "OK" -o ok.bin --mode binary
                  xxd -b -c 3 -g 1 -l 45 ok.bin | grep --color '11\\|$'

              # Binary packed — 1 binary group per row, bit pattern = pixels:
                python xxdart.py encode "OK" -o ok.bin --mode binary --binary-style packed
                  xxd -b -c 1 -g 1 -l 15 ok.bin | grep --color '11\\|$'

              # Horizontal layout — all chars side by side (short messages only):
                python xxdart.py encode "HI" -o hi.bin --layout horizontal
                  xxd -c 11 -g 2 -l 77 hi.bin | grep --color '#\\|$'

              # Add cover bytes (noise before the art):
                python xxdart.py encode "SECRET" -o out.bin \\
                  --start-offset 64 --noise random
                  xxd -c 5 -s 64 -g 2 -l 245 out.bin | grep --color '#\\|$'

            Key concept
            -----------
            Setting xxd's -c to the art's pixel-row width makes ONE xxd row =
            ONE pixel row.  Wrong -c wraps rows and destroys the picture.
            The flags ARE the decryption key — without them the file looks like
            random binary noise.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ── encode sub-command ────────────────────────────────────────────────────
    enc = sub.add_parser(
        "encode",
        help="Encode a secret message into a binary file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            Render a secret message as a bitmap font and write it into a binary
            file.  The art is only visible when xxd is run with the exact flags
            printed by this command (the "viewing key").

            After writing the file, the tool byte-verifies it, runs xxd, pipes
            the output through grep --color for immediate colourised display, and
            prints VERIFIED OK.

            ── MODES ────────────────────────────────────────────────────────────
            --mode ascii   (default)
              Art appears in xxd's right-hand ASCII column.
              Lit pixel  → 0x23 '#'  dark pixel → 0x2e '.'
              Font: 5-wide.  xxd flags: -c <w> -g 2 -l <size>
              Colour grep pattern: grep --color '#\\|$'

            --mode hex
              Art appears in xxd's hex data column.
              Each pixel writes 2 identical bytes: lit=0x88→'8888', dark=0x11→'1111'
              Dense figure-eight '8888' vs thin strokes '1111' for max contrast.
              Font: 5-wide.  xxd flags: -c <2w> -g 2 -l <size>
              Colour grep pattern: grep --color '88\\|$'

            --mode binary
              Art appears in xxd's binary column (xxd -b required automatically).
              Two styles via --binary-style:

              blocks (default)
                3-wide compact font.  Lit=0xff→'11111111', dark=0x00→'00000000'.
                xxd flags: -b -c 3 -g 1 -l <size>
                Colour grep pattern: grep --color '11\\|$'
                  11111111 11111111 11111111   ← lit row
                  11111111 00000000 11111111   ← mixed row

              packed
                5-wide font bit-packed into 1 byte per row (bit7=left pixel).
                xxd flags: -b -c 1 -g 1 -l <size>
                Colour grep pattern: grep --color '11\\|$'
                  11111000   ← '#####' top of 'I' = 11111 + 000 padding
                  00100000   ← '  #  ' centre of 'I'
                Only works with --layout vertical.

            ── LAYOUTS ──────────────────────────────────────────────────────────
            --layout vertical   (default)
              Each character is stacked below the previous.  Row width is always
              equal to the glyph width (5 bytes ascii/hex, 3 bytes binary/blocks,
              1 byte binary/packed).  Works for messages of any length.

            --layout horizontal
              All characters placed side by side in one wide row.  Row width
              grows with message length; xxd's hard limit of 256 bytes/row caps
              this at ~42 characters.  Not supported with --binary-style packed.

            ── xxd FORMATTING FLAGS (the viewing key) ───────────────────────────
            --cols-per-row N   xxd -c N   bytes per row (auto-computed if omitted)
            --start-offset N   xxd -s N   skip N cover bytes before the art
            --group N          xxd -g N   hex grouping (default: 2 ascii/hex, 1 binary)
            --limit N          xxd -l N   limit output to N bytes (default: art size)
            Note: -b is added automatically for --mode binary.

            ── PIXEL BYTE VALUES ────────────────────────────────────────────────
            --art-char CHAR    ASCII mode only.  Single printable character for
                               lit pixels.  Convenience shorthand for --on-byte.
                               Cannot be combined with --on-byte.  '.' is
                               forbidden (it is the background pixel).
            --on-byte BYTE     Byte value for lit pixels (decimal or 0xNN hex).
                               Defaults: ascii=0x23, hex=0x88, binary=0xff.
            --off-byte BYTE    Byte value for dark pixels.
                               Defaults: ascii=0x2e, hex=0x11, binary=0x00.
                               Must differ from --on-byte.

            ── COVER BYTES ──────────────────────────────────────────────────────
            --start-offset N   Prepend N bytes before the art (the receiver must
                               use xxd -s N to skip them).  Default: 0.
            --noise zeros|random
                               Content of the cover bytes.  Default: zeros.

            ── COLOUR HIGHLIGHTING ──────────────────────────────────────────────
            The tool automatically pipes xxd output through grep --color when
            displaying the verification output.  The VIEWING KEY section prints
            both the plain xxd command and the colour-pipe version.

            Grep patterns per mode (to avoid false highlights on the address):
              ascii  : grep --color '#\\|$'   (or your --art-char value)
              hex    : grep --color '88\\|$'  (two-digit lit group)
              binary : grep --color '11\\|$'  (two-bit match, not single '1')

            ── EXAMPLES ─────────────────────────────────────────────────────────
            # Default ascii mode, vertical layout:
              python xxdart.py encode "HELLO" -o secret.bin
              View: xxd -c 5 -g 2 -l 35 secret.bin | grep --color '#\\|$'

            # Custom ink character:
              python xxdart.py encode "HELLO" -o secret.bin --art-char '*'
              View: xxd -c 5 -g 2 -l 35 secret.bin | grep --color '\\*\\|$'

            # Hex mode:
              python xxdart.py encode "KEY" -o key.bin --mode hex
              View: xxd -c 10 -g 2 -l 161 key.bin | grep --color '88\\|$'

            # Binary blocks:
              python xxdart.py encode "OK" -o ok.bin --mode binary
              View: xxd -b -c 3 -g 1 -l 45 ok.bin | grep --color '11\\|$'

            # Binary packed (cleanest single-group view):
              python xxdart.py encode "OK" -o ok.bin --mode binary --binary-style packed
              View: xxd -b -c 1 -g 1 -l 15 ok.bin | grep --color '11\\|$'

            # Horizontal layout (short messages):
              python xxdart.py encode "HI" -o hi.bin --layout horizontal
              View: xxd -c 11 -g 2 -l 77 hi.bin | grep --color '#\\|$'

            # With cover bytes and random noise:
              python xxdart.py encode "TOP SECRET" -o payload.bin \\
                --start-offset 64 --noise random
              View: xxd -c 5 -s 64 -g 2 -l 595 payload.bin | grep --color '#\\|$'

            # Full control — override every parameter:
              python xxdart.py encode "CODE" -o out.bin \\
                --mode hex --start-offset 32 --noise random \\
                --on-byte 0xDB --off-byte 0x00 --group 2
        """),
    )
    enc.add_argument(
        "message",
        help=(
            "The secret message to encode.  Surround with quotes if it contains "
            "spaces.  Unsupported characters are skipped with a warning."
        ),
    )
    enc.add_argument(
        "-o", "--output",
        required=True,
        metavar="FILE",
        help="Path of the binary file to write.",
    )
    enc.add_argument(
        "--mode",
        choices=["ascii", "hex", "binary"],
        default="ascii",
        help=(
            "Where the art appears in xxd output.  'ascii': ASCII column (default). "
            "'hex': hex data column.  'binary': binary column (adds -b to xxd command)."
        ),
    )
    enc.add_argument(
        "--layout",
        choices=["vertical", "horizontal"],
        default="vertical",
        help=(
            "How characters are arranged.  'vertical' (default): each character is "
            "stacked below the previous one; row width is always 5 bytes, so any "
            "message length works.  'horizontal': all characters side by side in one "
            "wide row; limited to ~42 characters before hitting xxd's 256-byte/row cap."
        ),
    )
    enc.add_argument(
        "--binary-style",
        choices=["blocks", "packed"],
        default="blocks",
        help=(
            "Encoding style for --mode binary only.  "
            "'blocks' (default): uses a 3-wide compact font; each pixel is 0xff or "
            "0x00, so xxd -b -c 3 shows 3 binary groups (24 bits) per row — "
            "11111111 00000000 11111111.  "
            "'packed': uses the 5-wide font; each pixel row is bit-packed into one "
            "byte (left-aligned, bit7=first pixel), so xxd -b -c 1 shows exactly "
            "1 binary group per row — the 8-bit pattern IS the pixel row.  "
            "Packed gives the cleanest single-group display and works only with "
            "--layout vertical."
        ),
    )

    # ── xxd formatting flags ──────────────────────────────────────────────────
    xxd_group = enc.add_argument_group(
        "xxd formatting flags (the viewing key)",
        description=(
            "These options map directly to xxd flags.  Omit any to use the "
            "mode-specific default.  Supply a value to override it exactly."
        ),
    )
    xxd_group.add_argument(
        "--cols-per-row",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Bytes per xxd row (= xxd -c N).  Auto-computed from message pixel "
            "width if omitted.  Must be >= natural message width.  Larger values "
            "right-pad each row with the off-byte."
        ),
    )
    xxd_group.add_argument(
        "--start-offset",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Prepend N cover bytes before the art (= xxd -s N).  The receiver "
            "must use the same -s value to skip these bytes.  Default: 0."
        ),
    )
    xxd_group.add_argument(
        "--group",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Hex grouping size (= xxd -g N).  Default: 2 (ascii, groups pairs "
            "of bytes in the hex column), 2 (hex, shows each 2-byte pixel as a "
            "4-char group '8888'/'1111'), 1 (binary, separates each byte cleanly)."
        ),
    )
    xxd_group.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Limit xxd output to N bytes after the -s skip (= xxd -l N).  "
            "Default: art_size bytes (7 x cols_per_row), which trims output "
            "to exactly the art section."
        ),
    )

    # ── pixel byte values ─────────────────────────────────────────────────────
    byte_group = enc.add_argument_group(
        "pixel byte values",
        description="Control what byte is written for lit and dark pixels.",
    )
    byte_group.add_argument(
        "--art-char",
        type=str,
        default=None,
        metavar="CHAR",
        help=(
            "ASCII mode only.  Single printable character used for lit pixels "
            "(the 'ink' of the art).  Convenience shorthand for --on-byte.  "
            "Cannot be used together with --on-byte.  Default: '#'.  "
            "Note: '.' is forbidden — it is the background character and would "
            "make the art invisible."
        ),
    )
    byte_group.add_argument(
        "--on-byte",
        type=lambda x: int(x, 0),
        default=None,
        metavar="BYTE",
        help=(
            "Byte value for a lit pixel.  Accepts decimal or hex (0x23).  "
            "Defaults: ascii=0x23 '#', hex=0x88, binary=0xff.  "
            "For ascii mode prefer --art-char for convenience."
        ),
    )
    byte_group.add_argument(
        "--off-byte",
        type=lambda x: int(x, 0),
        default=None,
        metavar="BYTE",
        help=(
            "Byte value for a dark pixel.  Accepts decimal or hex (0x2e).  "
            "Defaults: ascii=0x2e '.', hex=0x11, binary=0x00.  "
            "Must differ from --on-byte."
        ),
    )

    # ── cover byte options ────────────────────────────────────────────────────
    cover_group = enc.add_argument_group(
        "cover bytes",
        description="Options for the block of bytes prepended before the art.",
    )
    cover_group.add_argument(
        "--noise",
        choices=["random", "zeros"],
        default="zeros",
        help=(
            "Content of the cover bytes.  'zeros': all null bytes (default).  "
            "'random': random values — makes the file look like noise throughout."
        ),
    )

    args = parser.parse_args()

    if args.command == "encode":
        encode(args)


if __name__ == "__main__":
    main()


# ═══════════════════════════════════════════════════════════════════════════════
#  README
# ═══════════════════════════════════════════════════════════════════════════════
#
#  QUICK-START EXAMPLES
#  --------------------
#
#  1. ASCII mode (art in xxd's ASCII column):
#
#       python xxdart.py encode "TOP SECRET" -o payload.bin \
#         --mode ascii --start-offset 64 --noise random
#
#       Receiver runs the printed key:
#         xxd -c 59 -s 64 -g 2 -l 413 payload.bin
#
#       The rightmost column reveals the art:
#         00000040: 232e … 23  #####..###..#####.…
#
#  2. Hex mode (art in xxd's hex column, high-contrast 88/11):
#
#       python xxdart.py encode "HI" -o hex.bin --mode hex
#
#       xxd -c 11 -g 1 -l 77 hex.bin
#
#       The hex column shows dense "88" blocks vs thin "11":
#         00000000: 88 11 11 11 88 11 88 88 88 88 88  .....……
#
#  3. Binary mode (art in xxd's binary column via -b):
#
#       python xxdart.py encode "OK" -o bits.bin --mode binary
#
#       xxd -b -c 11 -g 1 -l 77 bits.bin
#
#       Solid 11111111 blocks vs empty 00000000:
#         00000000: 00000000 11111111 11111111 …  ......
#
#  4. Full flag control (override every xxd formatting parameter):
#
#       python xxdart.py encode "CODE" -o out.bin \
#         --mode hex --cols-per-row 30 --start-offset 128 \
#         --group 2 --limit 300 --noise random \
#         --on-byte 0xDB --off-byte 0x00
#
#  KEY CONCEPT
#  -----------
#  The font is 5x7 pixels.  A message of N characters produces a bitmap
#  7 rows tall and (N*5 + (N-1)*1) = (6N-1) bytes wide.
#
#  Setting xxd's -c to that width makes ONE xxd row = ONE pixel row.
#  Wrong -c wraps rows and destroys the picture — the flags ARE the key.
#
#  Mode defaults:
#    ascii  : on=0x23 '#'      off=0x2e '.'     -g 2  (art in ASCII col)
#    hex    : on=0x88 "88"     off=0x11 "11"    -g 1  (art in hex col)
#    binary : on=0xff 11111111 off=0x00 00000000 -g 1  (art in binary col)
# ═══════════════════════════════════════════════════════════════════════════════
