# pause

The `pause` module provides behaviors that pause execution for a specified duration. Pauses can be uniform-random (between a low and high bound) or schedule-driven (defined in a YAML file with time windows and variance).

All pause behaviors return `RUNNING` while the pause is active and `SUCCESS` once the wait time has elapsed.

## Classes and Functions

---

### `PauseUniform`

A leaf behavior that pauses for a random duration drawn uniformly from `[low, high)`.

```python
PauseUniform(name, low, high)
```

| Parameter | Type | Description |
|---|---|---|
| `name` | `str` | Name of this behavior node |
| `low` | `float` | Minimum pause duration in seconds |
| `high` | `float` | Maximum pause duration in seconds |

**Returns:** `RUNNING` until the elapsed time reaches the sampled pause duration, then `SUCCESS`.

**Example**

```python
from py_branches.pause import PauseUniform

# Pause for between 2 and 5 seconds
pause = PauseUniform(name="ShortPause", low=2.0, high=5.0)
```

**Notes:**
- The random duration is sampled once on `initialise` using `numpy.random.uniform`.
- A new duration is sampled on each subsequent activation (i.e. after the behavior terminates and is re-entered).

---

### `load_schedule_file`

Loads and preprocesses a YAML pause schedule file.

```python
load_schedule_file(file_path)
```

| Parameter | Type | Description |
|---|---|---|
| `file_path` | `str` | Path to the YAML schedule file |

**Returns:** A preprocessed schedule list suitable for passing to `CheckPauseSchedule` and `PauseSchedule`.

**YAML format**

Each entry defines a pause window with an optional random variance applied to the stop time:

```yaml
- start_pause_time: "22:30:00"
  stop_pause_time: "06:30:00"
  variance: "0:30:00"
- start_pause_time: "12:30:00"
  stop_pause_time: "16:30:00"
  variance: "0:30:00"
```

- `start_pause_time` / `stop_pause_time`: Wall-clock times in `HH:MM:SS` format.
- `variance`: A `±` random offset applied to the stop time. If `"0:30:00"`, the actual stop time is sampled from `[stop - 30min, stop + 30min]`.
- Windows that cross midnight (e.g. `22:30` → `06:30`) are handled automatically.

**Example**

```python
from py_branches.pause import load_schedule_file

schedule = load_schedule_file("configs/schedules/example_schedule.yaml")
```

---

### `CheckPauseSchedule`

A leaf behavior that returns `SUCCESS` when the current wall-clock time falls inside any window in the schedule, and `FAILURE` otherwise.

```python
CheckPauseSchedule(name, schedule)
```

| Parameter | Type | Description |
|---|---|---|
| `name` | `str` | Name of this behavior node |
| `schedule` | `list` | Preprocessed schedule from `load_schedule_file` |

**Returns:** `SUCCESS` if the current time is within a pause window; `FAILURE` otherwise.

**Example**

```python
from py_branches.pause import load_schedule_file, CheckPauseSchedule

schedule = load_schedule_file("configs/schedules/my_schedule.yaml")
check = CheckPauseSchedule(name="IsScheduledPause", schedule=schedule)
```

**Notes:**
- Once a window is matched, the same window will not re-trigger until after it ends, preventing repeated matches within a single window.
- Typical use: as the condition in a behavior tree branch that switches to pause mode during scheduled downtime.

---

### `PauseSchedule`

A leaf behavior that pauses until the end of the currently active schedule window (with variance applied).

```python
PauseSchedule(name, schedule)
```

| Parameter | Type | Description |
|---|---|---|
| `name` | `str` | Name of this behavior node |
| `schedule` | `list` | Preprocessed schedule from `load_schedule_file` |

**Returns:** `RUNNING` until the current schedule window's stop time is reached, then `SUCCESS`.

**Example**

```python
from py_branches.pause import load_schedule_file, PauseSchedule

schedule = load_schedule_file("configs/schedules/my_schedule.yaml")
pause = PauseSchedule(name="ScheduledPause", schedule=schedule)
```

**Notes:**
- On `initialise`, calculates how many seconds remain until the end of the current window.
- A new random variance offset is applied each time the behavior is re-entered.

---

## Schedule-Based Pause Pattern

A common pattern is to check the schedule and, if in a pause window, wait until the window ends:

```python
import py_trees
from py_branches.pause import load_schedule_file, CheckPauseSchedule, PauseSchedule

schedule = load_schedule_file("configs/schedules/example_schedule.yaml")

check = CheckPauseSchedule(name="CheckSchedule", schedule=schedule)
pause = PauseSchedule(name="WaitForWindowEnd", schedule=schedule)

# Sequence: if currently in a pause window, then wait until it ends
pause_branch = py_trees.composites.Sequence(name="PauseBranch", memory=True)
pause_branch.add_children([check, pause])

# Selector: try the pause branch; if not in a window, proceed normally
root = py_trees.composites.Selector(name="Root", memory=False)
root.add_children([pause_branch, main_behavior])
```
