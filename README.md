# py_branches

`py_branches` provides higher-level functionality designed to sit on top of the [py_trees](https://py-trees.readthedocs.io/) library. It extends py_trees with reusable behaviors and decorators for common patterns such as alternating execution, probabilistic selection, blackboard-driven conditionals, and time-based pausing.

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
| `alternating` | Cycle through behaviors in fixed patterns or run a child every N ticks |
| `blackboard` | Read/write/gate behaviors based on py_trees blackboard variables |
| `pause` | Time-based pauses — uniform random duration or YAML-defined schedules |
| `random` | Probabilistic behavior execution and weighted random selectors |

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
from py_branches.pause import load_schedule_file, CheckPauseSchedule, PauseSchedule

schedule = load_schedule_file("configs/schedules/example_schedule.yaml")

# Returns SUCCESS when the current time falls inside a scheduled window
check = CheckPauseSchedule(name="CheckSchedule", schedule=schedule)

# Pauses until the current scheduled window ends
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

## Running Tests

```bash
pytest tests/
```

## Documentation

Detailed documentation for each module is in the [`docs/`](docs/) folder:

- [alternating.md](docs/alternating.md) — Alternating and periodic execution
- [blackboard.md](docs/blackboard.md) — Blackboard-driven behaviors
- [pause.md](docs/pause.md) — Time-based pausing and schedules
- [random.md](docs/random.md) — Probabilistic execution

## License

BSD License. See [LICENSE](LICENSE) for details.
