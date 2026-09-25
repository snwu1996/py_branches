# py_branches

`py_branches` provides higher-level functionality designed to sit on top of the
[py_trees](https://py-trees.readthedocs.io/) library. py_trees supplies the
machinery for behavior trees; this package supplies the patterns that otherwise
get rewritten on top of it — alternating execution, probabilistic selection,
blackboard-driven conditionals, rate limiting, retries, and time-based pausing.

## Installation

```bash
pip install py_branches
```

Or from source:

```bash
git clone https://github.com/snwu1996/py_branches.git
cd py_branches
pip install -e .
```

## Modules

| Module | Description |
|---|---|
| {doc}`alternating` | Cycle through behaviors in fixed patterns, or run a child every N ticks |
| {doc}`blackboard` | Read, write, and gate execution on py_trees blackboard variables |
| {doc}`cooldown` | Enforce a minimum time gap between runs of a child |
| {doc}`counter` | Cap the total number of times a child runs |
| {doc}`latch` | Make a child's first SUCCESS permanent |
| {doc}`pause` | Time-based pauses — random, sampled, keyboard, or YAML-scheduled |
| {doc}`random` | Probabilistic execution and weighted random selection |
| {doc}`retry` | Re-run a child that fails, optionally with a delay |
| {doc}`timeout` | Fail a child that stays RUNNING too long |
| {doc}`visitors` | Log status transitions and time spent RUNNING |

## Finding the right module

Most of what is here answers one of three questions.

**Should this child run at all?** {doc}`alternating` decides by tick count or an
external switch, {doc}`random` by chance, {doc}`blackboard` by the value of a
shared variable, {doc}`cooldown` by how long it has been since the last run, and
{doc}`counter` and {doc}`latch` by whether it has already run enough times.

**How long may it take?** {doc}`timeout` bounds a single run; {doc}`retry`
handles the case where the answer is "take another go".

**How do I see what happened?** {doc}`visitors` — attached to the tree rather
than placed in it, so they observe without altering control flow.

{doc}`pause`, uniquely, is the tree deliberately doing nothing for a while.

## A note on `success_if_skip`

Most decorators here take a `success_if_skip` flag, and it is the most common
source of confusion. When a decorator skips its child, it still has to report
*something*, and which status is right depends on the composite above it: under
a Selector, FAILURE reads as "try the next child"; under a Sequence, FAILURE
aborts everything after it, so SUCCESS is what makes a skip invisible.

The defaults are not uniform — the gates in {doc}`blackboard` default to
`True`, while the decorators in {doc}`alternating` and {doc}`random` default to
`False`. Check the page for the class you are using.

```{toctree}
:maxdepth: 2
:caption: Modules
:hidden:

alternating
blackboard
cooldown
counter
latch
pause
random
retry
timeout
visitors
```

## Indices

* {ref}`genindex`
* {ref}`modindex`
