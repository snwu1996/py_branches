# alternating

The `alternating` module provides decorators and factory functions for controlling *which* behaviors run and *when* — cycling through a list in a fixed pattern, or gating a child to run only every N ticks or within a specific tick window.

## Classes and Functions

---

### `ActivateBehavior`

A decorator that enables or disables its child behavior via an external `activate` flag.

When deactivated, the child's `initialise` and `update` methods are never called. This is used internally by `run_alternating` but can also be used standalone to externally gate any behavior.

**Constructor**

```python
ActivateBehavior(child, name="ActivateBehavior", success_if_skip=False)
```

| Parameter | Type | Description |
|---|---|---|
| `child` | `Behaviour` | The behavior to wrap |
| `name` | `str` | Name of this decorator node |
| `success_if_skip` | `bool` | Return `SUCCESS` instead of `FAILURE` when deactivated (default `False`) |

**Properties**

```python
decorator.activate        # getter — bool
decorator.activate = True # setter — enable or disable the child
```

**Example**

```python
from py_branches.alternating import ActivateBehavior
import py_trees

child = py_trees.behaviours.Success(name="Child")
gate = ActivateBehavior(child, name="Gate", success_if_skip=True)

gate.activate = False  # child will be skipped, returns SUCCESS
gate.activate = True   # child runs normally
```

---

### `run_alternating`

Factory function that creates a `Selector` which cycles through a list of behaviors, running each one for a fixed number of consecutive ticks before moving to the next.

```python
run_alternating(name, behaviors, counts)
```

| Parameter | Type | Description |
|---|---|---|
| `name` | `str` | Name of the root `Selector` node |
| `behaviors` | `list[Behaviour]` | Behaviors to cycle through |
| `counts` | `list[int]` | Number of ticks each behavior runs before switching. Must be same length as `behaviors`. |

**Returns:** `py_trees.composites.Selector`

**Example**

```python
from py_branches.alternating import run_alternating
import py_trees

a = py_trees.behaviours.Success(name="A")
b = py_trees.behaviours.Success(name="B")
c = py_trees.behaviours.Success(name="C")

# A runs for 3 ticks, B for 2, C for 4, then repeats
root = run_alternating("Cycle", [a, b, c], [3, 2, 4])
```

**Tick sequence:** `A A A B B C C C C A A A B B ...`

---

### `RunEveryX`

A decorator that executes its child only once every X ticks, where X is drawn randomly from a given range at the start of each cycle.

```python
RunEveryX(child, name="RunEveryX", every_x_range=(1, 1), success_if_skip=False)
```

| Parameter | Type | Description |
|---|---|---|
| `child` | `Behaviour` | The behavior to wrap |
| `name` | `str` | Name of this decorator node |
| `every_x_range` | `tuple[int, int]` | `(min, max)` — X is sampled uniformly from this range each cycle |
| `success_if_skip` | `bool` | Return `SUCCESS` instead of `FAILURE` on skipped ticks (default `False`) |

**Example**

```python
from py_branches.alternating import RunEveryX
import py_trees

child = py_trees.behaviours.Success(name="Child")

# Run exactly every 5th tick
every_5 = RunEveryX(child, name="Every5", every_x_range=(5, 5))

# Run at a random interval between 1 and 5 ticks
random_interval = RunEveryX(child, name="RandomInterval", every_x_range=(1, 5))
```

**Behavior:** On ticks where the child is skipped, returns `FAILURE` (or `SUCCESS` if `success_if_skip=True`). A new X value is sampled after each execution.

---

### `RunEveryRange`

A decorator that executes its child only during a specific range of iterations within a fixed cycle length.

```python
RunEveryRange(child, name="RunEveryRange", max_range=1, run_range=(1, 1), success_if_skip=False)
```

| Parameter | Type | Description |
|---|---|---|
| `child` | `Behaviour` | The behavior to wrap |
| `name` | `str` | Name of this decorator node |
| `max_range` | `int` | Total cycle length (resets after this many ticks) |
| `run_range` | `tuple[int, int]` | `(start, end)` — inclusive iteration range during which the child runs |
| `success_if_skip` | `bool` | Return `SUCCESS` instead of `FAILURE` on skipped ticks (default `False`) |

**Example**

```python
from py_branches.alternating import RunEveryRange
import py_trees

child = py_trees.behaviours.Success(name="Child")

# Run on iterations 4, 5, 6 out of every 10-tick cycle
# Tick pattern: F F F E E E F F F F (F=skip, E=execute), repeating
windowed = RunEveryRange(child, name="Window", max_range=10, run_range=(4, 6))
```

**Behavior:** The internal iteration counter runs from 1 to `max_range`, then resets to 1. The child runs when `run_range[0] <= counter <= run_range[1]`.
