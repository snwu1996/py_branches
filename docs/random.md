# random

The `random` module provides a decorator and a factory function for probabilistic behavior execution. Use these when you want a behavior to run only some of the time, or when you want to select randomly from a set of behaviors with defined weights.

## Classes and Functions

---

### `RandomRun`

A decorator that executes its child with a given probability. On each cycle, a single random draw determines whether the child runs.

```python
RandomRun(child, name="RandomRun", probability=1.0, success_if_skip=False)
```

| Parameter | Type | Description |
|---|---|---|
| `child` | `Behaviour` | The behavior to wrap |
| `name` | `str` | Name of this decorator node |
| `probability` | `float` | Probability `[0.0, 1.0]` that the child runs on a given tick |
| `success_if_skip` | `bool` | Return `SUCCESS` instead of `FAILURE` when the child is skipped (default `False`) |

**Returns:**
- If the random draw succeeds: the child's status (`SUCCESS`, `FAILURE`, or `RUNNING`).
- If the random draw fails: `SUCCESS` if `success_if_skip=True`, else `FAILURE`.

**Example**

```python
from py_branches.random import RandomRun
import py_trees

child = py_trees.behaviours.Success(name="Child")

# 70% chance the child runs each tick; otherwise returns FAILURE
maybe = RandomRun(child, name="MaybeRun", probability=0.7)

# 30% chance — returns SUCCESS when skipped (transparent to parent Selector)
sometimes = RandomRun(child, name="Sometimes", probability=0.3, success_if_skip=True)
```

**Notes:**
- The random draw is made once on `initialise` and holds for the duration of that execution (until the behavior terminates).
- A new draw is made on the next `initialise` call (i.e. the next activation).
- `probability=0.0` means the child never runs; `probability=1.0` means it always runs.

---

### `random_selector`

Factory function that creates a `Selector` where each child has a specified absolute probability of being selected on any given tick.

```python
random_selector(name, behaviors, probabilities)
```

| Parameter | Type | Description |
|---|---|---|
| `name` | `str` | Name of the root `Selector` node |
| `behaviors` | `list[Behaviour]` | Behaviors to choose from |
| `probabilities` | `list[float]` | Absolute probability for each behavior. Must sum to `1.0` and be the same length as `behaviors`. |

**Returns:** `py_trees.composites.Selector`

**Example**

```python
from py_branches.random import random_selector
import py_trees

a = py_trees.behaviours.Success(name="A")
b = py_trees.behaviours.Success(name="B")
c = py_trees.behaviours.Success(name="C")

# A is chosen 20% of the time, B 30%, C 50%
selector = random_selector("WeightedChoice", [a, b, c], [0.2, 0.3, 0.5])
```

**How it works:**

A standard `Selector` tries children left-to-right, stopping at the first `SUCCESS`. `random_selector` wraps each behavior in a `RandomRun` decorator and recalculates *conditional* probabilities so that the absolute probability of each behavior being selected matches the values you provide.

For example, given `[0.2, 0.3, 0.5]`:
- Behavior A is given probability `0.2` (20% chance it runs and succeeds, stopping the selector).
- Behavior B is given probability `0.3 / 0.8 ≈ 0.375` (conditional on A being skipped).
- Behavior C is given probability `1.0` (runs whenever A and B are both skipped).

The result is that over many ticks, each behavior is selected with the intended absolute frequency.

**Notes:**
- Probabilities must sum to `1.0`.
- The list order matters: lower-index behaviors are evaluated first in the underlying `Selector`.
- This is useful for simulating stochastic agent decisions or varying behavior profiles.

---

## Combining with Other Modules

`RandomRun` and `run_alternating` can be combined — for instance, to probabilistically skip a behavior within a cycling pattern:

```python
from py_branches.alternating import run_alternating
from py_branches.random import RandomRun
import py_trees

a = py_trees.behaviours.Success(name="A")
b = py_trees.behaviours.Success(name="B")

# Wrap B so it only runs 50% of the time when it's B's turn
b_maybe = RandomRun(b, name="MaybeB", probability=0.5, success_if_skip=True)

root = run_alternating("AlternateWithRandom", [a, b_maybe], [3, 2])
```
