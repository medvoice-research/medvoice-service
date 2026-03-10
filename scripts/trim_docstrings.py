#!/usr/bin/env python3
"""Trim Args/Returns/Raises sections from docstrings in Python files.

Rules:
1. Remove Args:, Returns:, Raises: sections (and their indented content)
2. Keep the description line(s) if non-obvious
3. Remove the entire docstring if the remaining description just restates the function name
4. Keep short single-line docstrings unchanged
5. Never touch config files (config.py, settings.py, etc.)
"""

import re
import sys
from pathlib import Path

# Files to never modify — operational docs (e.g. Raises in config) are valuable
CONFIG_FILE_PATTERNS = {
    "config.py",
    "settings.py",
    "conf.py",
    "configuration.py",
    "database.py",
}


def is_config_file(filepath: Path) -> bool:
    """Check if a file is a configuration file that should be skipped."""
    return filepath.name in CONFIG_FILE_PATTERNS


def is_self_explanatory(description: str, func_name: str) -> bool:
    """Check if description merely restates the function name."""
    if not description.strip():
        return True

    desc_lower = description.strip().lower().rstrip(".")
    # Convert func_name to words: get_audio_duration -> ['get', 'audio', 'duration']
    name_words = set(func_name.lower().replace("_", " ").split())
    desc_words = set(desc_lower.split())

    # If description is very short and almost all words come from function name
    if len(desc_words) <= 4 and len(name_words & desc_words) >= len(name_words) - 1:
        return True

    return False


def trim_docstring_content(docstring: str, func_name: str = "") -> str | None:
    """Trim Args/Returns/Raises from a docstring. Returns None to remove entirely."""
    # Remove the triple quotes
    if docstring.startswith('"""') and docstring.endswith('"""'):
        inner = docstring[3:-3]
    elif docstring.startswith("'''") and docstring.endswith("'''"):
        inner = docstring[3:-3]
    else:
        return docstring

    # Check if it contains Args:/Returns:/Raises:
    if not re.search(r"\n\s*(Args|Returns|Raises|Attributes):", inner):
        return docstring  # No sections to trim, keep as-is

    # Extract description (everything before first section header)
    parts = re.split(r"\n\s*(Args|Returns|Raises|Attributes):", inner, maxsplit=1)
    description = parts[0].strip()

    if not description:
        return None  # No description, remove entirely

    # Check if description is self-explanatory
    if func_name and is_self_explanatory(description, func_name):
        return None  # Remove entirely

    # Return trimmed docstring with just description
    return f'"""{description}"""'


def process_file(filepath: Path) -> tuple[bool, int]:
    """Process a single Python file. Returns (changed, count_of_changes)."""
    content = filepath.read_text()
    lines = content.split("\n")
    new_lines = []
    i = 0
    changes = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        # Detect start of a docstring that may span multiple lines
        if '"""' in stripped or "'''" in stripped:
            quote = '"""' if '"""' in stripped else "'''"
            indent = line[: len(line) - len(stripped)]

            # Check if it's a single-line docstring
            if stripped.count(quote) >= 2 and stripped.endswith(quote):
                # Single-line docstring — keep as-is
                new_lines.append(line)
                i += 1
                continue

            # Multi-line docstring — collect all lines
            docstring_lines = [line]
            i += 1
            while i < len(lines):
                docstring_lines.append(lines[i])
                if quote in lines[i] and lines[i].strip().endswith(quote):
                    break
                i += 1
            i += 1

            full_docstring_text = "\n".join(docstring_lines)

            # Check if this docstring has Args:/Returns:/Raises:
            if re.search(r"\n\s*(Args|Returns|Raises|Attributes):", full_docstring_text):
                # Find the function name from the line above the docstring
                func_name = ""
                for prev_idx in range(len(new_lines) - 1, max(len(new_lines) - 5, -1), -1):
                    prev_line = new_lines[prev_idx].strip()
                    func_match = re.match(r"(?:async\s+)?def\s+(\w+)", prev_line)
                    if func_match:
                        func_name = func_match.group(1)
                        break

                # Extract inner content
                ds_start = full_docstring_text.find(quote)
                ds_end = full_docstring_text.rfind(quote) + len(quote)
                raw_docstring = full_docstring_text[ds_start:ds_end]

                trimmed = trim_docstring_content(raw_docstring, func_name)

                if trimmed is None:
                    # Remove the docstring entirely
                    changes += 1
                    continue
                elif trimmed != raw_docstring:
                    # Replace with trimmed version
                    new_lines.append(f"{indent}{trimmed}")
                    changes += 1
                    continue

            # No change needed
            new_lines.extend(docstring_lines)
            continue

        new_lines.append(line)
        i += 1

    if changes > 0:
        filepath.write_text("\n".join(new_lines))

    return changes > 0, changes


def main():
    base_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

    # Directories to scan
    target_dirs = [
        "app",
        "tests",
    ]

    total_changes = 0
    files_changed = 0
    files_skipped = 0

    for d in target_dirs:
        dir_path = base_dir / d
        if dir_path.exists():
            for py_file in sorted(dir_path.rglob("*.py")):
                if is_config_file(py_file):
                    files_skipped += 1
                    continue

                changed, count = process_file(py_file)
                if changed:
                    print(f"  ✓ {py_file.relative_to(base_dir)}: {count} docstring(s) trimmed")
                    files_changed += 1
                    total_changes += count

    if total_changes == 0:
        print("No verbose docstrings found — codebase is clean.")
    else:
        print(f"\nDone: {total_changes} docstring(s) trimmed across {files_changed} file(s)")
    if files_skipped:
        print(f"Skipped {files_skipped} config file(s)")


if __name__ == "__main__":
    main()
