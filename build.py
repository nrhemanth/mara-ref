"""
build.py — Bundle a modular Opentrons protocol into one flat file.

Usage:
    python build.py protocols/imod_quasi2D.py
    python build.py protocols/imod_quasi2D.py --out dist/imod_bundled.py

The bundler:
  1. Parses all `import` / `from ... import` lines in the entry file.
  2. For each import that maps to a local .py file, recursively inlines its
     content (stripping that file's own local imports).
  3. Collects all external imports (opentrons, pandas, stdlib, …) and writes
     them once at the top, deduplicated.
  4. Writes: header → external imports → inlined local code → entry-point body.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def module_to_path(module_name: str) -> Path | None:
    """Convert a dotted module name to a .py path relative to ROOT, or None."""
    candidate = ROOT / Path(*module_name.split(".")).with_suffix(".py")
    if candidate.exists():
        return candidate
    # also try it as a package __init__
    init = ROOT / Path(*module_name.split(".")) / "__init__.py"
    if init.exists():
        return init
    return None


def is_local_import(module_name: str) -> bool:
    return module_to_path(module_name) is not None


def parse_imports(source: str) -> tuple[list[str], list[str]]:
    """
    Return (local_modules, external_import_lines).

    local_modules  — dotted module names that resolve to a local file
    external_lines — raw import lines to keep verbatim
    """
    local_modules: list[str] = []
    external_lines: list[str] = []

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"  Warning: syntax error while parsing imports: {e}", file=sys.stderr)
        return [], []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if is_local_import(alias.name):
                    local_modules.append(alias.name)
                else:
                    line = f"import {alias.name}"
                    if alias.asname:
                        line += f" as {alias.asname}"
                    external_lines.append(line)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level  # relative import dots (e.g. from . import X)
            if level == 0 and is_local_import(module):
                local_modules.append(module)
            else:
                names = ", ".join(
                    (f"{a.name} as {a.asname}" if a.asname else a.name)
                    for a in node.names
                )
                dots = "." * level
                line = f"from {dots}{module} import {names}"
                external_lines.append(line)

    return local_modules, external_lines


def strip_import_lines(source: str) -> str:
    """Remove all import statements from source text."""
    lines = source.splitlines(keepends=True)
    out = []
    skip_next_continuation = False

    for line in lines:
        stripped = line.lstrip()
        if skip_next_continuation:
            if not line.rstrip().endswith("\\"):
                skip_next_continuation = False
            continue
        if stripped.startswith("import ") or stripped.startswith("from "):
            if line.rstrip().endswith("\\"):
                skip_next_continuation = True
            continue
        out.append(line)

    return "".join(out)


# ---------------------------------------------------------------------------
# Recursive bundler
# ---------------------------------------------------------------------------

def bundle(
    entry: Path,
    visited: set[Path] | None = None,
) -> tuple[list[str], list[str]]:
    """
    Recursively process `entry` and all its local dependencies.

    Returns:
        external_imports — deduplicated list of external import lines
        body_blocks      — list of code blocks (one per file, imports stripped)
    """
    if visited is None:
        visited = set()

    entry = entry.resolve()
    if entry in visited:
        return [], []
    visited.add(entry)

    source = entry.read_text(encoding="utf-8")
    local_modules, external_lines = parse_imports(source)

    all_external: list[str] = list(external_lines)
    all_bodies: list[str] = []

    for mod in local_modules:
        dep_path = module_to_path(mod)
        if dep_path is None:
            print(f"  Warning: could not resolve local module '{mod}'", file=sys.stderr)
            continue
        print(f"  inlining {dep_path.relative_to(ROOT)}")
        dep_external, dep_bodies = bundle(dep_path, visited)
        all_external.extend(dep_external)
        all_bodies.extend(dep_bodies)

    body = strip_import_lines(source).strip()
    if body:
        label = entry.relative_to(ROOT)
        all_bodies.append(f"# ── inlined from {label} ──────────────────────────\n{body}")

    return all_external, all_bodies


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Bundle Opentrons protocol into one file.")
    parser.add_argument("entry", help="Entry-point protocol file (e.g. protocols/imod_quasi2D.py)")
    parser.add_argument("--out", help="Output path (default: dist/<entry-stem>_bundled.py)")
    args = parser.parse_args()

    entry = Path(args.entry).resolve()
    if not entry.exists():
        sys.exit(f"Error: {entry} not found")

    if args.out:
        out_path = Path(args.out)
    else:
        dist = ROOT / "dist"
        dist.mkdir(exist_ok=True)
        out_path = dist / f"{entry.stem}_bundled.py"

    print(f"Bundling {entry.relative_to(ROOT)} ...")
    external_imports, body_blocks = bundle(entry)

    # Deduplicate external imports, preserving order
    seen: set[str] = set()
    deduped_imports: list[str] = []
    for line in external_imports:
        if line not in seen:
            seen.add(line)
            deduped_imports.append(line)

    output_parts = [
        "# AUTO-GENERATED by build.py — do not edit by hand.",
        f"# Source: {entry.relative_to(ROOT)}",
        "",
        "\n".join(deduped_imports),
        "",
    ]
    output_parts.extend(block + "\n" for block in body_blocks)

    out_path.write_text("\n".join(output_parts), encoding="utf-8")
    print(f"Written to {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
