# py_branches

[![CI](https://github.com/snwu1996/py_branches/actions/workflows/ci.yml/badge.svg)](https://github.com/snwu1996/py_branches/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/snwu1996/py_branches/branch/main/graph/badge.svg)](https://codecov.io/gh/snwu1996/py_branches)
[![PyPI](https://img.shields.io/pypi/v/py_branches)](https://pypi.org/project/py_branches/)
[![Docs](https://readthedocs.org/projects/py-branches/badge/?version=latest)](https://py-branches.readthedocs.io/en/latest/)

**Reusable behavior-tree behaviors and decorators for Python, built on [py_trees](https://py-trees.readthedocs.io/).**

`py_branches` provides higher-level functionality designed to sit on top of the [py_trees](https://py-trees.readthedocs.io/) library. py_trees supplies the machinery for behavior trees; this package supplies the patterns that otherwise get rewritten on top of it — alternating execution, probabilistic selection, blackboard-driven conditionals, cooldowns, run caps, latching, retries, timeouts, and time-based pausing.

## Installation

**From PyPI:**
```bash
pip install py_branches
```

**From source (editable):**
```bash
git clone https://github.com/snwu1996/py_branches.git
cd py_branches
pip install -e .
```

## Modules

| Module | Description |
|---|---|
| [`alternating`](https://py-branches.readthedocs.io/en/latest/alternating.html) | Cycle through behaviors in fixed patterns, or run a child every N ticks |
| [`blackboard`](https://py-branches.readthedocs.io/en/latest/blackboard.html) | Read, write, and gate execution on py_trees blackboard variables |
| [`cooldown`](https://py-branches.readthedocs.io/en/latest/cooldown.html) | Enforce a minimum time gap between runs of a child |
| [`counter`](https://py-branches.readthedocs.io/en/latest/counter.html) | Cap the total number of times a child runs |
| [`latch`](https://py-branches.readthedocs.io/en/latest/latch.html) | Make a child's first SUCCESS permanent |
| [`pause`](https://py-branches.readthedocs.io/en/latest/pause.html) | Time-based pauses — random, sampled, keyboard, or YAML-scheduled |
| [`random`](https://py-branches.readthedocs.io/en/latest/random.html) | Probabilistic execution and weighted random selection |
| [`retry`](https://py-branches.readthedocs.io/en/latest/retry.html) | Re-run a child that fails, optionally with a delay |
| [`timeout`](https://py-branches.readthedocs.io/en/latest/timeout.html) | Fail a child that stays RUNNING too long |
| [`visitors`](https://py-branches.readthedocs.io/en/latest/visitors.html) | Log status transitions and time spent RUNNING |

## Basic Usage

### Alternating — cycle through behaviors

```python
import py_trees
from py_branches.alternating import run_alternating

a = py_trees.behaviours.Success(name="A")
b = py_trees.behaviours.Success(name="B")
c = py_trees.behaviours.Success(name="C")

# Run A for 3 ticks, then B for 2 ticks, then C for 4 ticks, then repeat
root = run_alternating("Alternating", [a, b, c], [3, 2, 4])
```

### Alternating — run a child every N ticks

```python
from py_branches.alternating import RunEveryX, RunEveryRange

child = py_trees.behaviours.Success(name="Child")

# Run child every 5th tick
every_5 = RunEveryX(child, name="Every5", every_x_range=(5, 5))

# Run child only on iterations 4–6 out of every 10
windowed = RunEveryRange(child, name="Window", max_range=10, run_range=(4, 6))
```

### Blackboard — conditional execution and variable management

```python
import py_trees
from py_branches.blackboard import (
    IncrementBlackboardVariable,
    RunIfBlackboardVariableEquals,
    SetBlackboardVariableIfCondition,
)

# Set up blackboard
py_trees.blackboard.Blackboard.enable_activity_stream()
client = py_trees.blackboard.Client(name="setup")
client.register_key("counter", access=py_trees.common.Access.WRITE)
client.counter = 0

# Increment a blackboard counter each tick
increment = IncrementBlackboardVariable(
    name="Increment", variable_name="counter", increment_by=1
)

# Only run a child behavior when counter == 5
child = py_trees.behaviours.Success(name="AtFive")
gate = RunIfBlackboardVariableEquals(
    child, name="RunAt5", variable_name="counter", equals=5
)
```

### Pause — random duration pause

```python
from py_branches.pause import PauseUniform

# Pause for a random duration between 1.0 and 3.0 seconds
pause = PauseUniform(name="RandomPause", low=1.0, high=3.0)
```

### Pause — schedule-based pause

```python
from py_branches.pause import load_schedule_file, PauseSchedule

schedule = load_schedule_file("configs/schedules/example_schedule.yaml")
if schedule is None:
    raise SystemExit("schedule file is empty")

# Pauses until the current scheduled window ends; SUCCESS immediately if
# outside all windows.
pause = PauseSchedule(name="PauseSchedule", schedule=schedule)
```

### Random — probabilistic execution

```python
import py_trees
from py_branches.random import RandomRun, random_selector

child = py_trees.behaviours.Success(name="Child")

# Execute child with 70% probability; return FAILURE otherwise
maybe = RandomRun(child, name="Maybe", probability=0.7)

# Weighted random selector: a=20%, b=30%, c=50%
a = py_trees.behaviours.Success(name="A")
b = py_trees.behaviours.Success(name="B")
c = py_trees.behaviours.Success(name="C")
selector = random_selector("WeightedSel", [a, b, c], [0.2, 0.3, 0.5])
```

### Cooldown, Counter, Latch — limit how often a child runs

```python
import py_trees
from py_branches.cooldown import Cooldown
from py_branches.counter import Counter
from py_branches.latch import Latch

child = py_trees.behaviours.Success(name="Child")

# At most one run every 10 seconds; FAILURE while still cooling down
cooled = Cooldown(child, name="Cooldown", duration=10.0)

# Run at most 3 times, then report SUCCESS without ticking the child again
capped = Counter(child, name="Counter", num_runs=3)

# Once the child succeeds, keep reporting SUCCESS forever
latched = Latch(child, name="Latch")
```

### Retry and Timeout — bound failure and duration

```python
from py_branches.retry import Retry
from py_branches.timeout import Timeout

# Re-run on FAILURE up to 3 attempts, waiting 0.5s between them
retried = Retry(child, name="Retry", max_attempts=3, delay=0.5)

# FAILURE if the child stays RUNNING for more than 2 seconds
bounded = Timeout(child, name="Timeout", duration=2.0)
```

### Visitors — see what the tree actually did

```python
from py_branches.visitors import StatusTransitionVisitor, TimerVisitor

tree = py_trees.trees.BehaviourTree(root=child)

# Log a line only when a leaf changes status, and time every RUNNING stretch
tree.visitors.append(StatusTransitionVisitor())
tree.visitors.append(TimerVisitor())
```

## Running Tests

```bash
pytest tests/
```

## Documentation

Full documentation, including an API reference generated from the source
and rendered behavior-tree diagrams, is at
[py-branches.readthedocs.io](https://py-branches.readthedocs.io/en/latest/).

To build it locally:

```bash
poetry install --with docs
poetry run sphinx-build -b html docs docs/_build/html
```

Rendering the diagrams needs the `dot` binary (`apt install graphviz`).

## License

BSD License. See [LICENSE](LICENSE) for details.
