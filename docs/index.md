# py_branches

`py_branches` provides higher-level functionality designed to sit on top of the
[py_trees](https://py-trees.readthedocs.io/) library. It extends py_trees with
reusable behaviors and decorators for common patterns such as alternating
execution, probabilistic selection, blackboard-driven conditionals, and
time-based pausing.

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
| {doc}`alternating` | Cycle through behaviors in fixed patterns or run a child every N ticks |
| {doc}`blackboard` | Read/write/gate behaviors based on py_trees blackboard variables |
| {doc}`pause` | Time-based pauses — uniform random duration or YAML-defined schedules |
| {doc}`random` | Probabilistic behavior execution and weighted random selectors |

```{toctree}
:maxdepth: 2
:caption: Module guides

alternating
blackboard
pause
random
```

## Indices

* {ref}`genindex`
* {ref}`modindex`
