#!/usr/bin/env python3
"""Check that pyproject.toml's version was bumped relative to the base branch.

Two checks run against the head revision's pyproject.toml:

1. ``[project].version`` and ``[tool.poetry].version`` agree (both are declared,
   so bumping one and forgetting the other is the easy mistake).
2. The head version is strictly greater than the base version.

Usage:
    python scripts/check_version_bump.py --base <base.toml> --head <head.toml>

Exits 0 when both checks pass, 1 otherwise. Requires Python 3.11+ (tomllib).
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

# (epoch-less) release segment plus an optional pre/post/dev suffix, e.g. 1.2.3rc1
_VERSION_RE = re.compile(r"^(\d+(?:\.\d+)*)(.*)$")


def read_versions(path: Path) -> tuple[str, str]:
    """Return (project_version, poetry_version) from a pyproject.toml."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    project = data.get("project", {}).get("version")
    poetry = data.get("tool", {}).get("poetry", {}).get("version")

    if project is None and poetry is None:
        fail(f"{path}: no version found in [project] or [tool.poetry]")

    return project, poetry


def release_key(version: str) -> tuple[int, ...]:
    """Comparable tuple for the numeric release segment of a version string."""
    match = _VERSION_RE.match(version.strip())
    if match is None:
        fail(f"cannot parse version {version!r}")
    assert match is not None  # for type checkers; fail() is NoReturn
    return tuple(int(part) for part in match.group(1).split("."))


def compare(head: str, base: str) -> int:
    """Return -1/0/1 comparing head against base by release segment."""
    head_key, base_key = release_key(head), release_key(base)
    # Zero-pad so 0.8 and 0.8.0 compare equal.
    width = max(len(head_key), len(base_key))
    head_key += (0,) * (width - len(head_key))
    base_key += (0,) * (width - len(base_key))
    return (head_key > base_key) - (head_key < base_key)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path,
                        help="pyproject.toml as it exists on the base branch")
    parser.add_argument("--head", required=True, type=Path,
                        help="pyproject.toml from the pull request head")
    args = parser.parse_args()

    head_project, head_poetry = read_versions(args.head)
    base_project, base_poetry = read_versions(args.base)

    # 1. The two declarations in the head file must agree.
    if head_project is not None and head_poetry is not None and head_project != head_poetry:
        fail(
            "pyproject.toml versions disagree: "
            f"[project].version = {head_project!r}, "
            f"[tool.poetry].version = {head_poetry!r}. "
            "Bump both."
        )

    head = head_project or head_poetry
    base = base_project or base_poetry
    assert head is not None and base is not None

    # 2. The head version must be strictly newer than the base.
    result = compare(head, base)
    if result == 0:
        fail(
            f"version is still {head} — bump it in pyproject.toml "
            "([project].version and [tool.poetry].version), "
            "or add the 'no-version-bump' label to this pull request."
        )
    if result < 0:
        fail(f"version went backwards: {base} (base) -> {head} (head).")

    print(f"ok: version bumped {base} -> {head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
