#!/usr/bin/env python3
"""Render and parse the release questionnaire posted on pull requests.

The questionnaire is a sticky PR comment with checkboxes. A contributor ticks
the boxes; when the PR merges, the same comment is parsed to decide whether to
tag a release. Answers are keyed by invisible HTML comments (``<!--k:tag-yes-->``)
rather than by their prose, so the labels can be reworded without breaking the
parse.

Usage:
    python scripts/release_questionnaire.py render --head-version 1.5.2 \
        --base-version 1.5.1 --base-ref main [--preserve-from old-comment.md]
    python scripts/release_questionnaire.py parse --body-file comment.md

``render`` writes the comment body to stdout; ``--preserve-from`` carries the
ticks in an existing body across a re-render, so refreshing the comment after a
push does not wipe the answers. ``parse`` writes ``key=value`` lines to stdout
(append them to ``$GITHUB_OUTPUT``) and exits 1 on contradictory answers.
"""

from __future__ import annotations

import argparse
import sys
import re
from pathlib import Path

# Every questionnaire comment starts with this so the workflow can find the one
# it posted earlier instead of adding a new comment on each push.
MARKER = "<!-- release-questionnaire -->"

# A box for key ``k``: "- [x] ... <!--k:tag-yes-->". The key comment sits at end
# of line, which is where render() puts it.
_BOX_RE = re.compile(r"^\s*[-*]\s*\[(?P<mark>[ xX])\].*<!--k:(?P<key>[\w-]+)-->\s*$")


def render(
    head_version: str,
    base_version: str,
    base_ref: str,
    checked: frozenset[str] = frozenset(),
) -> str:
    """Return the comment body for a PR at *head_version*.

    Keys in *checked* are rendered already ticked.
    """
    def box(key: str, label: str) -> str:
        mark = "x" if key in checked else " "
        return f"- [{mark}] {label} <!--k:{key}-->"

    status = (
        f"bumped from `{base_version}` on `{base_ref}`"
        if head_version != base_version
        else f"**unchanged** from `{base_ref}` — tagging will fail until it is bumped"
    )
    lines = [
        MARKER,
        "## Release questionnaire",
        "",
        f"Version in this PR: `{head_version}` ({status})",
        "",
        "Tick the boxes below, then merge. The answers are read **at merge "
        "time**, so edits up to the moment of merge count.",
        "",
        "**Tag a release for this PR?**",
        box("tag-yes", f"Yes — tag `v{head_version}` and publish to PyPI on merge"),
        box("tag-no", "No — merge without tagging"),
        "",
        "**If yes, also:**",
        box("github-release", "Create a GitHub Release with auto-generated notes"),
        box("prerelease", "Mark it a pre-release"),
        "",
        "<sub>Leaving every box unticked means no tag. Posted by "
        "`.github/workflows/release-questionnaire.yml`.</sub>",
    ]
    return "\n".join(lines) + "\n"


def parse(body: str) -> dict[str, bool]:
    """Return {key: checked} for every keyed checkbox found in *body*."""
    answers: dict[str, bool] = {}
    for line in body.splitlines():
        match = _BOX_RE.match(line)
        if match:
            answers[match["key"]] = match["mark"].lower() == "x"
    return answers


def decide(answers: dict[str, bool]) -> dict[str, str]:
    """Collapse raw answers into workflow outputs; raise on a contradiction."""
    if answers.get("tag-yes") and answers.get("tag-no"):
        raise ValueError(
            "both 'Yes' and 'No' are ticked in the release questionnaire; "
            "untick one before merging"
        )
    tag = answers.get("tag-yes", False)
    return {
        "tag": str(tag).lower(),
        # Only meaningful when tagging; forced false otherwise so a stray tick
        # on a no-tag PR cannot cut a release on its own.
        "github_release": str(tag and answers.get("github-release", False)).lower(),
        "prerelease": str(tag and answers.get("prerelease", False)).lower(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    render_cmd = sub.add_parser("render", help="print the questionnaire body")
    render_cmd.add_argument("--head-version", required=True)
    render_cmd.add_argument("--base-version", required=True)
    render_cmd.add_argument("--base-ref", default="main")
    render_cmd.add_argument(
        "--preserve-from",
        help="existing comment body whose ticks should be carried over",
    )

    parse_cmd = sub.add_parser("parse", help="print key=value answers")
    parse_cmd.add_argument(
        "--body-file", required=True, help="file holding the comment body"
    )

    args = parser.parse_args()

    if args.command == "render":
        checked: frozenset[str] = frozenset()
        if args.preserve_from:
            previous = Path(args.preserve_from)
            if previous.is_file():
                checked = frozenset(
                    key for key, on in parse(previous.read_text("utf-8")).items() if on
                )
        print(
            render(args.head_version, args.base_version, args.base_ref, checked),
            end="",
        )
        return 0

    try:
        outputs = decide(parse(Path(args.body_file).read_text("utf-8")))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for key, value in outputs.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
