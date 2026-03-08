# blackboard

The `blackboard` module provides behaviors and decorators that read from and write to the [py_trees blackboard](https://py-trees.readthedocs.io/en/devel/blackboards.html) — a shared key-value store used for inter-behavior communication. These classes let you increment counters, set flags, and gate execution based on blackboard state without writing custom behaviors from scratch.

## Prerequisites

Before using any blackboard behavior, the py_trees blackboard must be initialized and the relevant keys must be registered:

```python
import py_trees

py_trees.blackboard.Blackboard.enable_activity_stream()
client = py_trees.blackboard.Client(name="setup")
client.register_key("my_var", access=py_trees.common.Access.WRITE)
client.my_var = 0
```

## Classes

---

### `IncrementBlackboardVariable`

A behavior (leaf node) that increments a numeric blackboard variable on each tick.

```python
IncrementBlackboardVariable(name, variable_name, increment_by=1.0)
```

| Parameter | Type | Description |
|---|---|---|
| `name` | `str` | Name of this behavior node |
| `variable_name` | `str` | Blackboard key to increment (must be `int` or `float`) |
| `increment_by` | `float` | Amount to add each tick (default `1.0`) |

**Returns:** `SUCCESS` after incrementing. `FAILURE` if the variable does not exist or is not a numeric type.

**Example**

```python
from py_branches.blackboard import IncrementBlackboardVariable

counter = IncrementBlackboardVariable(
    name="IncrementCounter", variable_name="counter", increment_by=1
)
```

---

### `IncrementBlackboardVariableIfCondition`

A decorator that increments a blackboard variable only when its child returns a specified status.

```python
IncrementBlackboardVariableIfCondition(
    child, name, variable_name, condition, increment_by=1.0
)
```

| Parameter | Type | Description |
|---|---|---|
| `child` | `Behaviour` | The behavior to wrap |
| `name` | `str` | Name of this decorator node |
| `variable_name` | `str` | Blackboard key to increment |
| `condition` | `py_trees.common.Status` | Status that triggers the increment (e.g. `Status.SUCCESS`) |
| `increment_by` | `float` | Amount to add (default `1.0`) |

**Returns:** The child's status, unchanged.

**Example**

```python
import py_trees
from py_branches.blackboard import IncrementBlackboardVariableIfCondition

child = py_trees.behaviours.Success(name="Child")

# Increment "success_count" each time child returns SUCCESS
counter = IncrementBlackboardVariableIfCondition(
    child,
    name="CountSuccesses",
    variable_name="success_count",
    condition=py_trees.common.Status.SUCCESS,
    increment_by=1,
)
```

---

### `SetBlackboardVariableIfCondition`

A decorator that sets a blackboard variable to a fixed value when its child returns a specified status.

```python
SetBlackboardVariableIfCondition(child, name, variable_name, condition, set_to)
```

| Parameter | Type | Description |
|---|---|---|
| `child` | `Behaviour` | The behavior to wrap |
| `name` | `str` | Name of this decorator node |
| `variable_name` | `str` | Blackboard key to set |
| `condition` | `py_trees.common.Status` | Status that triggers the assignment |
| `set_to` | `any` | Value to write to the blackboard key |

**Returns:** The child's status, unchanged.

**Example**

```python
import py_trees
from py_branches.blackboard import SetBlackboardVariableIfCondition

child = py_trees.behaviours.Failure(name="Child")

# Reset "is_active" to False whenever the child fails
reset = SetBlackboardVariableIfCondition(
    child,
    name="ResetOnFailure",
    variable_name="is_active",
    condition=py_trees.common.Status.FAILURE,
    set_to=False,
)
```

---

### `RunIfBlackboardVariableEquals`

A decorator that runs its child only when a blackboard variable equals a specified value. On other ticks it returns a fixed status without executing the child.

```python
RunIfBlackboardVariableEquals(
    child, name, variable_name, equals, success_if_skip=True
)
```

| Parameter | Type | Description |
|---|---|---|
| `child` | `Behaviour` | The behavior to wrap |
| `name` | `str` | Name of this decorator node |
| `variable_name` | `str` | Blackboard key to check |
| `equals` | `any` | Value to compare against |
| `success_if_skip` | `bool` | Return `SUCCESS` instead of `FAILURE` when condition is not met (default `True`) |

**Returns:** The child's status when the condition is met; `SUCCESS` or `FAILURE` (based on `success_if_skip`) otherwise.

**Example**

```python
import py_trees
from py_branches.blackboard import RunIfBlackboardVariableEquals

child = py_trees.behaviours.Success(name="SpecialAction")

# Only run SpecialAction when "mode" equals "fast"
gated = RunIfBlackboardVariableEquals(
    child,
    name="RunIfFast",
    variable_name="mode",
    equals="fast",
    success_if_skip=True,
)
```

## Combining Blackboard Behaviors

These classes compose naturally. For example, increment a counter on each tick and only run a special action when it reaches a threshold:

```python
import py_trees
from py_branches.blackboard import (
    IncrementBlackboardVariable,
    RunIfBlackboardVariableEquals,
)

py_trees.blackboard.Blackboard.enable_activity_stream()
client = py_trees.blackboard.Client(name="setup")
client.register_key("tick_count", access=py_trees.common.Access.WRITE)
client.tick_count = 0

increment = IncrementBlackboardVariable(
    name="Tick", variable_name="tick_count", increment_by=1
)
special = py_trees.behaviours.Success(name="SpecialOnTick5")
gate = RunIfBlackboardVariableEquals(
    special, name="RunAt5", variable_name="tick_count", equals=5
)

root = py_trees.composites.Sequence(name="Root", memory=True)
root.add_children([increment, gate])
```
