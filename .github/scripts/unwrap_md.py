#!/usr/bin/env python3
"""Join hard-wrapped Markdown lines so GitHub release notes render full width.

Release bodies turn every newline into a line break, so a CHANGELOG wrapped at ~90
columns shows up as short lines. A line is treated as a continuation (joined onto the
previous one) unless it is blank, a heading, a list item, a table row, a quote, a code
fence, or follows a blank line / heading. Fenced code blocks are left untouched.
Usage: unwrap_md.py < in.md > out.md
"""
import re
import sys

BLOCK_START = re.compile(r"^\s*([-*+]\s|\d+[.)]\s|#|\||>|```|~~~)")

out: list[str] = []
in_fence = False
for raw in sys.stdin.read().splitlines():
    line = raw.rstrip()
    if line.lstrip().startswith(("```", "~~~")):
        in_fence = not in_fence
        out.append(line)
        continue
    prev = out[-1] if out else ""
    joinable = (
        not in_fence
        and line.strip()
        and not BLOCK_START.match(line)
        and prev.strip()
        and not prev.lstrip().startswith(("#", "|", "```", "~~~"))
    )
    if joinable:
        out[-1] = prev + " " + line.strip()
    else:
        out.append(line)
print("\n".join(out).strip("\n"))
