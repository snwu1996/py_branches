# blackboard

The [py_trees blackboard](https://py-trees.readthedocs.io/en/devel/blackboards.html)
is a shared key-value store that lets behaviors communicate without being
wired directly to each other. This module packages the patterns that otherwise
get rewritten as one-off behaviors in every project: counting, flag-setting,
and gating a branch on a variable's value.

## Writers and gates

The classes split cleanly in two. **Writers** have an effect on the blackboard:
`IncrementBlackboardVariable` as a leaf, and
`IncrementBlackboardVariableIfCondition` / `SetBlackboardVariableIfCondition`
as decorators that pass their child's status through untouched and write as a
side effect. **Gates** — the three `RunIf...` decorators — read a variable and
decide whether to tick their child at all.

## Seeding a variable first

Every class here registers the key it touches, so you never need to register
one yourself. What you do need is for the value to exist before a reader or an
incrementer runs, because neither creates it:

```python
import py_trees

client = py_trees.blackboard.Client(name="setup")
client.register_key("tick_count", access=py_trees.common.Access.WRITE)
client.tick_count = 0
```

`SetBlackboardVariableIfCondition` is the exception — it overwrites whatever is
there, or creates the key.

## Failures are quiet

A missing or wrongly-typed variable never raises. The affected behavior logs a
warning and reports FAILURE; a gate treats the condition as unmet. This keeps a
mistyped key from taking down a running tree, at the cost of making it easy to
miss — so if a branch silently never runs, check the log for warnings from
`_get_and_check` before assuming the logic is wrong.

One sharp edge follows from it: a missing variable reads as `None`, so
`RunIfBlackboardVariableEquals(..., equals=None)` matches a variable that was
never set just as readily as one deliberately set to `None`. The numeric gates
do not have this problem — they check for `None` explicitly and skip.

## When the condition is evaluated

The gates re-read the blackboard on each *fresh entry*, not on each tick, and
hold the result for as long as the child stays RUNNING. A long-running child
therefore finishes its work even if the variable changes underneath it. That is
usually what you want; if you need a gate that interrupts mid-execution, you
need a different construct.

## API

```{eval-rst}
.. automodule:: py_branches.blackboard
   :members:
```
