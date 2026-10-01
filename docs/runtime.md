# runtime

`TreeRunner` runs a behavior tree the way a long-lived process needs to be run:
at a fixed rate, with signals handled, with an exit code that means something,
and with teardown that happens whatever went wrong. `RequestShutdown` and its
relatives are how a tree asks to stop.

## `TreeRunner` vs `tick_tock`

py_trees already has a tick loop, and it is a good one. Before reaching for
anything here, know what `BehaviourTree.tick_tock()` already gives you:

| Already provided | py_trees API |
|---|---|
| Fixed-period pacing, drift-free | `tick_tock(period_ms=…)` |
| Bounded iterations | `number_of_iterations` |
| Stop on SUCCESS/FAILURE | `stop_on_terminal_state=True` |
| Per-tick hooks | `add_pre_tick_handler` / `add_post_tick_handler` |
| Cooperative stop at a loop boundary | `interrupt()` |
| Per-node teardown | `tree.shutdown()` |
| Setup with progress reporting | `tree.setup(timeout, visitor=…)` |

**If all you need is a paced loop, use `tick_tock`.** `TreeRunner` is for a
*process* — something that has to exit with a code a supervisor understands,
survive a `SIGTERM` from `systemctl stop`, and guarantee that every behavior
released its resources on the way out. None of that is `tick_tock`'s job, and
none of it is expressible through a single `interrupt_tick_tocking` boolean.

What `TreeRunner` adds:

- **Exit codes**, so a supervisor can tell a clean stop from a crash.
- **Signal handling**, including a second signal that forces the issue.
- **Teardown** on every exit path, in a defined order.
- **Setup diagnostics** that name the node setup stalled after.
- **pause / resume / step**, for reading a live tree.

The pacing expression itself is copied verbatim out of `tick_tock`. That part of
py_trees is already right, and a reimplementation would only be a chance to
diverge from it silently.

## Rate, not period

`TreeRunner` is configured in ticks per second. The period is the reciprocal,
and is derived:

```python
from py_branches.runtime import TreeRunner

TreeRunner(tree, rate=20.0)  # 20 Hz — a 0.05 s period
TreeRunner(tree, rate=0.5)  # one tick every two seconds
TreeRunner(tree, rate=None)  # free-running: no sleep at all
```

`rate` must be positive and finite, or `None`. The derived period is readable
back off the runner:

```python
runner = TreeRunner(tree, rate=20.0)
assert runner.period == 0.05
```

`rate=None` skips the sleep entirely and stops counting overruns, since with no
period there is nothing left to overrun.

### Overruns are counted, never compensated

A tick that takes longer than the period increments `runner.overruns` and logs a
rate-limited WARNING. The next tick then starts immediately — the loop does
**not** fire a burst of catch-up ticks to get back on schedule. In an RPA tree a
catch-up burst means a burst of clicks, which is exactly the wrong response to
being behind.

`runner.overruns` after a run is the useful number: a tree that overruns most
ticks is not running at the rate you configured, whatever the configuration
says.

## Stopping

`stop_on` decides whether a terminal status ends the run:

```python
import py_trees
from py_branches.runtime import TreeRunner

# Runs forever, until a signal or a shutdown request.
TreeRunner(tree, rate=20.0)

# Runs the tree once and reports which way it went.
TreeRunner(
    tree,
    rate=20.0,
    stop_on=(py_trees.common.Status.SUCCESS, py_trees.common.Status.FAILURE),
)
```

`max_ticks` bounds either shape, which is mostly useful in tests and demos.

`runner.stop(code)` is safe to call from a signal handler or another thread: it
sets a flag read at the top of the loop, so the tick in flight always completes.

## Exit codes

```{list-table}
:header-rows: 1
:widths: 10 90

* - Code
  - Meaning
* - `0`
  - `stop_on` reached with SUCCESS, `max_ticks` exhausted, or a shutdown request carrying 0
* - `1`
  - `stop_on` reached with FAILURE
* - `2`
  - setup failed — a timeout, or a behavior that raised during `setup()`
* - `70`
  - an exception escaped a tick (`EX_SOFTWARE`); teardown runs, then it re-raises
* - `130`
  - SIGINT (128 + 2)
* - `143`
  - SIGTERM (128 + 15)
* - *custom*
  - whatever a `ShutdownRequest` carried
```

Setup failure returns rather than raises, because it is an operational outcome
with a diagnostic message attached. An exception out of a *tick* is a bug: the
exit code is set to 70, teardown completes, and the exception is re-raised with
its traceback intact. A supervision layer that swallowed tracebacks would be
worse than the loop it replaced.

In a systemd unit:

```ini
[Service]
ExecStart=/usr/bin/my-tree-runner
# 0 is clean; 1 is "the tree failed", which we also treat as a clean exit.
SuccessExitStatus=0 1
Restart=on-failure
```

## Shutdown is requested, not thrown

### Why not `sys.exit()`

The obvious way to end a run from inside a tree is a behavior that calls
`sys.exit()`. It is worth being precise about what that costs, because the
damage is invisible until the one time you need the last tick.

`sys.exit()` raises `SystemExit` from inside `update()`, mid-tick. Reading
`py_trees.trees.BehaviourTree.tick()`, the consequences are:

1. **The tick's visitors never finalise.** `tick()` runs `visitor.initialise()`,
   then the tick, *then* the `finalise()` loop. An exception from a behavior
   skips that loop, so the final state is never published and never traced. The
   most interesting tick of the run is the one you lose.
2. **`tree.count` is never incremented** — it is the last statement in `tick()`.
3. **No behavior is stopped or shut down.** Parent composites never get to
   `stop()` their children, so no `terminate()` runs and anything holding a
   thread or a handle keeps holding it.

### The cooperative path

`RequestShutdown` writes a `ShutdownRequest` to a reserved blackboard key and
returns SUCCESS. The tick finishes normally; `TreeRunner` reads the key *after*
the tick returns and leaves at the loop boundary. Nothing is lost.

```python
import py_trees
from py_branches.runtime import RequestShutdown

root = py_trees.composites.Sequence(
    name="Bot",
    memory=False,
    children=[
        build_main_loop(),
        RequestShutdown(name="all_done", code=0, reason="inventory empty"),
    ],
)
```

The blackboard is the transport because it couples nothing. A tree ticked by
hand with no runner simply leaves the key set, which the caller can check
itself; and any visitor that snapshots the blackboard shows a pending shutdown
without needing to know this module exists.

The key is `py_branches/shutdown`, exported as `SHUTDOWN_KEY`. Treat it as
reserved. `clear_shutdown_request()` removes it, and `runner.restart()` does so
as part of its reset — worth knowing if you run several trees in one process,
since the blackboard is global.

**First write wins.** Two `RequestShutdown` nodes reached in one tick produce
the first one's exit code, logged deterministically rather than depending on
which way the tree happened to be traversed.

### `ExitBehavior`

A `RequestShutdown` with a shorter name and a default of `"exit"`:

```python
from py_branches.runtime import ExitBehavior

quit_cleanly = ExitBehavior(name="exit_bot", code=0)
```

`ExitBehavior(immediate=True)` raises the `ShutdownRequest` instead of filing
it. The runner catches it at the loop boundary and still tears down — but the
tick was abandoned where it stood, so that tick's visitors never finalised and
`tree.count` never incremented. **Prefer the default.** Reach for `immediate`
only when the tree must stop mid-action, and know that you are paying for it
with the last tick's observability.

### `RaiseBehavior`

For the branch that is only reachable once an assumption has already been
violated:

```python
from py_branches.runtime import RaiseBehavior

unreachable = RaiseBehavior(
    name="impossible",
    exception=lambda: AssertionError("bank was open and closed"),
)
```

Teardown runs and the exception is re-raised: exit code 70, traceback intact.

### Signals

SIGINT and SIGTERM synthesize the same request, carrying `128 + signum` — 130
and 143. One shutdown path, three sources.

A **second** signal force-quits: the runner restores the original handler and
re-raises immediately. That matters, because teardown itself can hang — a
visitor's `close()` waiting on a socket, a `terminate()` joining a stuck thread.
A graceful shutdown that cannot itself be interrupted is worse than none.

`signal.signal()` only works on the main thread. A runner started on a worker
thread logs once at DEBUG and runs without handlers rather than refusing to
start; for the same reason, its `setup()` falls back to waiting indefinitely,
because py_trees implements the setup timeout with `SIGUSR1`.

## Teardown

Runs on every exit path, in this order:

1. `tree.root.stop(INVALID)` — `terminate()` on every active behavior, releasing
   threads and handles.
2. `tree.shutdown()` — py_trees' per-node `shutdown()`.
3. Every visitor satisfying `Closeable`, each in its own `try`/`except` so one
   failure cannot keep the rest open.
4. Signal handlers restored.

Behaviors release *before* visitors close, because a `terminate()` may emit a
final status that should still reach the trace or the publisher. Closing the
publisher first would silently drop it.

`Closeable` is a {class}`typing.Protocol` — a visitor qualifies by having a
`close()` method and nothing else. That is deliberate: it means the runner never
has to name a particular visitor class in an `isinstance` check to know that it
holds a socket.

```python
class TraceVisitor(py_trees.visitors.VisitorBase):
    def close(self) -> None:
        self._handle.close()
```

## Setup diagnostics

`tree.setup()` reports a timeout as a bare `RuntimeError`, which says that
something hung without saying what. `TreeRunner.setup()` passes a progress
visitor and re-raises as `SetupError` naming the last node that completed:

```
SetupError: setup failed; last completed node was 'open_furnace_checksum'
            (timeout 15.0s)
```

Each node is also logged at DEBUG as it finishes, so a slow setup is visible
while it happens rather than only once it fails.

## pause, resume, step

Reading a live tree in a viewer while it free-runs at 20 Hz is miserable.
Single-ticking is the feature:

```python
runner.pause()  # holds at the next loop boundary
runner.step(1)  # one tick, then back to holding
runner.resume()  # release
```

A held loop sleeps in short slices rather than blocking, so it stays responsive
— `stop()` from a paused runner exits promptly rather than waiting for a resume.
All three are safe to call from a signal handler, which makes wiring SIGUSR1 to
a pause toggle and SIGUSR2 to a step a purely application-side decision.

## Migrating a hand-rolled loop

A loop of this shape — and they are common —

```python
def run_tree(tree):
    try:
        while True:
            tree.tick()
            time.sleep(0.05)  # drifts: the real period is tick + 50 ms
    except KeyboardInterrupt:
        pass
    finally:
        for visitor in tree.visitors:
            if isinstance(visitor, ZMQVisitor):
                visitor.close()  # and tree.shutdown() never runs
```

becomes:

```python
from py_branches.runtime import TreeRunner

exit_code = TreeRunner(tree, rate=20.0).run()
```

Note the behavior change: `sleep(0.05)` *after* the tick was never 20 Hz, so the
tree will now tick more often than it used to. Start at the rate you thought you
had, leave the overrun logging on, and let it tell you what the tree was
actually doing.

## API

```{eval-rst}
.. automodule:: py_branches.runtime
   :members:
```
