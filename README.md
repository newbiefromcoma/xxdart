# xxdart

Hide a secret message as ASCII art inside a binary file. The art is completely
invisible when the file is opened normally or viewed with default hex dump
settings. It only becomes visible when the file is examined with the GNU `xxd`
utility using a specific combination of flags — those flags are the **viewing
key**.

Give someone the binary file. Unless they run `xxd` with exactly the right
`-c`, `-s`, `-g`, and potentially `-b` flags, they will see nothing but noise.
Give them the key and the message is revealed instantly.

---

## Sample Output

<!-- Replace the line below with your screenshot or terminal recording -->
*[Insert screenshot of encode output and xxd reveal here]*

---

## How It Works

`xxdart` renders the message using an internal 5x7 monospace bitmap font. Each
character is 5 pixels wide and 7 pixels tall, with 1 blank pixel row separating
consecutive characters in vertical mode. The pixel grid is flattened row-by-row
into a sequence of bytes and written into the output file, optionally preceded
by a block of cover bytes.

The critical insight is that `xxd` displays its output in rows of a fixed byte
width controlled by `-c`. When `-c` is set to exactly the pixel-row width of
the art, each xxd output row corresponds to exactly one row of the bitmap. The
art snaps into alignment and becomes readable in the ASCII, hex, or binary
column of the dump. A wrong `-c` value causes rows to wrap at the wrong point,
turning the art into unreadable noise. The correct flags are a functional
decryption key.

**Font coverage:** A-Z, a-z (rendered as uppercase), 0-9, and the following
punctuation: `! " # $ % & ' ( ) * + , - . / : ; < = > ? @ [ ] ^ _ \` { | } ~`

### Vertical layout (default)

Characters stack downward, one below the next. Row width is always 5 bytes,
well within xxd's hard limit of 256 bytes per row. This layout works for
messages of any length.

```
cols (-c) = 5   (fixed, = GLYPH_W)
rows      = N x 7 + (N - 1) x 1   (7 pixel rows per glyph, 1 blank row between)
art bytes = rows x 5
```

Reading the xxd output top-to-bottom, each group of 7 rows is one character.

### Horizontal layout (--layout horizontal)

Characters are placed side by side in one wide row, the traditional banner
style. Row width grows linearly with the message and hits xxd's 256-byte cap
at approximately 42 characters.

```
cols (-c) = N x 5 + (N - 1) x 1 = 6N - 1
rows      = 7   (fixed)
art bytes = 7 x cols
```

Use this for short labels or banners where side-by-side text looks better.

---

## Requirements

- Python 3.10 or later (no third-party dependencies, stdlib only)
- GNU `xxd` for verification and viewing (part of `vim-common` on most systems)

Install `xxd` if missing:

```
# Debian / Ubuntu
sudo apt install xxd

# macOS (xxd ships with Vim)
brew install vim

# Fedora / RHEL
sudo dnf install vim-common
```

---

## Installation

No installation required. Copy `xxdart.py` to any location and run it directly:

```
python3 xxdart.py --help
```

To make it available as a command:

```
chmod +x xxdart.py
sudo cp xxdart.py /usr/local/bin/xxdart
xxdart encode "HELLO" -o out.bin
```

---

## Usage

```
python3 xxdart.py encode "MESSAGE" -o OUTPUT_FILE [options]
```

The tool prints a summary of what was written and then prints the exact `xxd`
command the receiver must run to reveal the hidden art. It also runs that
command itself for immediate verification.

For messages of any length, the default vertical layout always works. Use
`--layout horizontal` only for short messages (up to ~42 characters).

---

## Modes and Layouts

There are three hiding modes (selected with `--mode`) and two layout directions
(`--layout`). Modes and layouts are independent — any combination is valid.

### ascii (default)

The art appears in the rightmost ASCII column of `xxd`. Each lit pixel is
stored as a printable byte (default `0x23` = `#`) and each dark pixel as
another printable byte (default `0x2e` = `.`). Because both values are
printable ASCII, xxd renders them as their actual characters, and the
pattern is readable as ASCII art.

```
python3 xxdart.py encode "HELLO" -o secret.bin
```

Reveal command (printed by the tool):

```
xxd -c 29 -g 2 -l 203 secret.bin
```

Example xxd output (the art is in the rightmost column):

```
00000000: 2e23 2323 2e2e 2e2e 2323 2323 ...  .###...####
0000001d: 232e 2e2e 232e 232e 2e2e 232e ...  #...#.#...#
...
```

### hex

The art appears in the hex data column of `xxd`. Lit pixels are stored as
`0x88` and dark pixels as `0x11`. In the hex dump, `88` appears as dense
figure-eight shapes while `11` appears as thin vertical strokes, providing
the maximum visual contrast achievable with hex digit characters. Grouping
defaults to `-g 1` so each pixel byte is visually separated by a space.

```
python3 xxdart.py encode "HELLO" -o secret.bin --mode hex
```

Reveal command:

```
xxd -c 29 -g 1 -l 203 secret.bin
```

Example xxd output (the art is in the hex column):

```
00000000: 11 88 88 88 11 11 11 11 88 88 88 ...
0000001d: 88 11 11 11 88 11 88 11 11 11 88 ...
...
```

### binary

The art appears in the binary column of `xxd -b`. Two styles are available via
`--binary-style`.

#### blocks (default)

Uses a compact 3-wide font. Lit pixels are stored as `0xff` (`11111111`) and
dark pixels as `0x00` (`00000000`). Each row shows 3 binary groups — narrow
enough to fit comfortably in a standard terminal.

```
python3 xxdart.py encode "OK" -o secret.bin --mode binary
```

Reveal command:

```
xxd -b -c 3 -g 1 -l 45 secret.bin
```

Example xxd output:

```
00000000: 11111111 11111111 11111111  ...
00000003: 11111111 00000000 11111111  ...
00000006: 11111111 00000000 11111111  ...
00000009: 11111111 00000000 11111111  ...
0000000c: 11111111 00000000 11111111  ...
0000000f: 11111111 00000000 11111111  ...
00000012: 11111111 11111111 11111111  ...
00000015: 00000000 00000000 00000000  ...   <- blank row separator
```

#### packed

Uses the standard 5-wide font. Each pixel row is bit-packed into a single byte
(bit 7 = leftmost pixel, unused low bits are zero). `xxd -b -c 1` displays
exactly **1 binary group per line** — the 8-bit pattern is the pixel row itself.
This gives the highest readability: one line, one row, no scanning.

```
python3 xxdart.py encode "OK" -o secret.bin --mode binary --binary-style packed
```

Reveal command:

```
xxd -b -c 1 -g 1 -l 15 secret.bin
```

Example xxd output (`O` then `K`, 7 rows each, 1 blank separator):

```
00000000: 01110000  p     <- ' ### ' = 0 1 1 1 0 0 0 0
00000001: 10001000  .     <- '#   #' = 1 0 0 0 1 0 0 0
00000002: 10001000  .
00000003: 10001000  .
00000004: 10001000  .
00000005: 10001000  .
00000006: 01110000  p     <- bottom of O
00000007: 00000000  .     <- blank separator
00000008: 10001000  .     <- top of K
00000009: 10010000  .
0000000a: 10100000  .
0000000b: 11000000  .     <- crossbar of K
0000000c: 10100000  .
0000000d: 10010000  .
0000000e: 10001000  .
```

---

## All Options

### Required

| Option | Description |
|---|---|
| `message` | The secret message to hide. Quote it if it contains spaces. |
| `-o FILE`, `--output FILE` | Path of the output binary file to write. |

### Mode and Layout

| Option | Default | Description |
|---|---|---|
| `--mode ascii\|hex\|binary` | `ascii` | Where the art appears in xxd output. |
| `--layout vertical\|horizontal` | `vertical` | `vertical`: characters stack downward, works for any message length. `horizontal`: characters side by side, limited to ~42 characters. |
| `--binary-style blocks\|packed` | `blocks` | Binary mode only. `blocks`: 3-wide font, 3 groups per row (`11111111 00000000 11111111`). `packed`: 5-wide font, 1 group per row, the 8-bit pattern is the pixel row. Requires `--layout vertical`. |

### xxd Formatting Flags (the viewing key)

These options directly control the flags that must be passed to `xxd` to reveal
the art. If you omit an option, a sensible default is chosen automatically and
printed in the viewing key command. If you supply a value, it is used exactly.

| Option | xxd flag | Default | Description |
|---|---|---|---|
| `--cols-per-row N` | `-c N` | auto | Bytes per xxd row. Must equal the art's pixel-row width. Auto-computed from message length if omitted. Must not be less than the natural message width. |
| `--start-offset N` | `-s N` | `0` | Number of cover bytes prepended before the art. The receiver must use `-s N` with the same value to skip them. |
| `--group N` | `-g N` | `2` (ascii/hex), `1` (binary) | Hex grouping size. Affects how bytes are visually clustered in the hex column. Hex mode defaults to `-g 2` so each 2-byte pixel shows as a 4-char group (`8888`/`1111`). |
| `--limit N` | `-l N` | art size | Limit the xxd output to N bytes after the skip offset. Defaults to exactly the art size so output is trimmed cleanly. |

Note: the `-b` flag for binary mode is added automatically when `--mode binary`
is used. You do not pass it separately.

### Pixel Byte Values

| Option | Default (ascii) | Default (hex) | Default (binary/blocks) | Description |
|---|---|---|---|---|
| `--on-byte BYTE` | `0x23` (`#`) | `0x88` | `0xff` | Byte value written for each lit pixel. Accepts decimal or hex (`0x23`). Not used in `--binary-style packed`. |
| `--off-byte BYTE` | `0x2e` (`.`) | `0x11` | `0x00` | Byte value written for each dark pixel. Not used in `--binary-style packed`. |

### Cover Bytes

| Option | Default | Description |
|---|---|---|
| `--start-offset N` | `0` | Number of bytes to prepend before the art begins. |
| `--noise random\|zeros` | `zeros` | Content of the cover bytes. `random` fills with random values; `zeros` uses null bytes. |

---

## Full Examples

### Long message, vertical layout (default)

```
python3 xxdart.py encode "hi i am Jeeva, and this is my new tool xxdart" -o secret.bin
```

Output:

```
Wrote 1855 bytes -> secret.bin
  Message  : 'hi i am Jeeva, and this is my new tool xxdart'
  Mode     : ascii
  Layout   : vertical
  Art size : 371 rows x 5 cols = 1855 bytes
  Cover    : 0 bytes (zeros)

  VIEWING KEY
  xxd -c 5 -g 2 -l 1855 secret.bin
```

The xxd output (each group of 7 rows is one character):

```
00000000: 232e 2e2e 23  #...#    <- top of 'H'
00000005: 232e 2e2e 23  #...#
0000000a: 232e 2e2e 23  #...#
0000000f: 2323 2323 23  #####    <- crossbar of 'H'
00000014: 232e 2e2e 23  #...#
00000019: 232e 2e2e 23  #...#
0000001e: 232e 2e2e 23  #...#    <- bottom of 'H'
00000023: 2e2e 2e2e 2e  .....    <- blank row separator
00000028: 2323 2323 23  #####    <- top of 'I'
...
```

### Short message, horizontal layout

```
python3 xxdart.py encode "HI" -o hi.bin --layout horizontal
```

Reveal:

```
xxd -c 11 -g 2 -l 77 hi.bin
```

Output (both characters side by side across 7 rows):

```
00000000: 232e 2e2e 232e 2323 2323 23  #...#.#####
0000000b: 232e 2e2e 232e 2e2e 232e 2e  #...#...#..
00000016: 232e 2e2e 232e 2e2e 232e 2e  #...#...#..
00000021: 2323 2323 232e 2e2e 232e 2e  #####...#..
0000002c: 232e 2e2e 232e 2e2e 232e 2e  #...#...#..
00000037: 232e 2e2e 232e 2e2e 232e 2e  #...#...#..
00000042: 232e 2e2e 232e 2323 2323 23  #...#.#####
```

### With cover bytes and random noise

Cover bytes disguise the file start as noise. The receiver still needs `-s` to
skip to the art.

```
python3 xxdart.py encode "TOP SECRET" -o payload.bin \
  --start-offset 64 --noise random
```

Viewing key printed by the tool:

```
xxd -c 5 -s 64 -g 2 -l 595 payload.bin
```

### Hex mode, vertical (default layout)

```
python3 xxdart.py encode "CODE" -o code.bin \
  --mode hex \
  --start-offset 32 \
  --noise random
```

Viewing key:

```
xxd -c 5 -s 32 -g 1 -l 203 code.bin
```

### Hex mode with custom pixel bytes

```
python3 xxdart.py encode "KEY" -o key.bin \
  --mode hex \
  --on-byte 0xDB \
  --off-byte 0x00 \
  --group 1
```

### Binary blocks mode, vertical (default style)

```
python3 xxdart.py encode "OK" -o bits.bin --mode binary
```

Reveal:

```
xxd -b -c 3 -g 1 -l 45 bits.bin
```

Each character appears as 7 rows of 3 binary groups, stacked top-to-bottom:

```
00000000: 11111111 11111111 11111111  ...   <- top of O
00000003: 11111111 00000000 11111111  ...
0000000c: 11111111 00000000 11111111  ...
00000012: 11111111 11111111 11111111  ...   <- bottom of O
00000015: 00000000 00000000 00000000  ...   <- blank row
00000018: 10001000 10001000 10001000  ...   <- top of K is not shown (see packed for K)
...
```

### Binary packed mode, vertical (maximum readability)

```
python3 xxdart.py encode "OK" -o bits.bin --mode binary --binary-style packed
```

Reveal:

```
xxd -b -c 1 -g 1 -l 15 bits.bin
```

One line = one pixel row. The 8-bit pattern is read directly as the glyph:

```
00000000: 01110000  p   <- O row 0:  ' ### ' = 01110000
00000001: 10001000  .   <- O row 1:  '#   #' = 10001000
00000002: 10001000  .
00000003: 10001000  .
00000004: 10001000  .
00000005: 10001000  .
00000006: 01110000  p   <- O row 6 (bottom)
00000007: 00000000  .   <- blank separator
00000008: 10001000  .   <- K row 0:  '#   #' = 10001000
00000009: 10010000  .   <- K row 1:  '#  # ' = 10010000
0000000a: 10100000  .   <- K row 2:  '# #  ' = 10100000
0000000b: 11000000  .   <- K row 3:  '##   ' = 11000000
0000000c: 10100000  .
0000000d: 10010000  .
0000000e: 10001000  .
```

### Widen rows with --cols-per-row (add right-side padding)

```
python3 xxdart.py encode "OK" -o wide.bin --cols-per-row 16
```

Reveal:

```
xxd -c 16 -g 2 -l 240 wide.bin
```

---

## Self-Verification

After writing the output file, the tool automatically:

1. Re-reads the file and compares the written bytes against the expected bitmap
   (byte-level check).
2. Runs the exact viewing-key `xxd` command and captures its output.
3. Parses the relevant column (ASCII, hex, or binary) from each output line and
   compares it against the expected pixel row.
4. Prints the full `xxd` output so you can see the art immediately.
5. Prints `VERIFIED OK` on success, or a detailed mismatch report on failure.

If `xxd` is not installed, step 2-4 are skipped and a message is printed with
the install command. The file is still written and byte-verified.

---

## Understanding the Viewing Key

The tool prints a command like:

```
xxd -c 59 -s 64 -g 2 -l 413 payload.bin
```

Each flag is essential:

| Flag | Meaning | What breaks without it |
|---|---|---|
| `-c 59` | 59 bytes per row | Wrong value wraps rows at the wrong point; art is unreadable |
| `-s 64` | Skip 64 cover bytes | Shows cover bytes instead of art; first row is misaligned |
| `-g 2` | Group hex by 2 bytes | Spacing changes but art survives; must match what the tool assumed |
| `-l 413` | Show 413 bytes only | Without this, trailing file content appears below the art |

The receiver needs only the file and the key command — no other software.

---

## Edge Cases and Error Handling

**Unsupported characters** are skipped with a warning. Only characters present
in the internal font are rendered. The warning names each skipped character.

**Message too wide for horizontal layout** produces an error when the message
requires more than 256 bytes per row (roughly 43+ characters). The error message
names the required `-c` value and the character limit. Switch to the default
vertical layout to handle any message length.

**Message too wide for --cols-per-row** produces an error with the minimum
required width printed. Increase `--cols-per-row` or shorten the message.

**xxd not installed** produces a clear error on stderr. The file is still
written and byte-verified. The key command is still printed.

**Empty message after filtering** (all characters were unsupported) produces
an error and no file is written.

---

## Supported Characters

The internal 5x7 font covers the following characters:

```
A B C D E F G H I J K L M N O P Q R S T U V W X Y Z
a b c d e f g h i j k l m n o p q r s t u v w x y z  (rendered as uppercase)
0 1 2 3 4 5 6 7 8 9
! " # $ % & ' ( ) * + , - . / : ; < = > ? @
[ ] ^ _ ` { | } ~   (space)
```

---

## License

MIT
