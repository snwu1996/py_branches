# visitors

A visitor is called once per behavior per tick by the tree's own tick
machinery, which makes it the right place for anything you want to *observe*
without changing the tree's shape. Neither visitor here affects control flow.

## Attaching them

```{testcode}
import py_trees
from py_branches.visitors import StatusTransitionVisitor, TimerVisitor

root = py_trees.composites.Sequence(name="Root", memory=True)
tree = py_trees.trees.BehaviourTree(root)
tree.visitors.append(StatusTransitionVisitor())
tree.visitors.append(TimerVisitor())
```

## What each one reports

`StatusTransitionVisitor` logs a leaf's status only when it *changes*. On a tree
ticking at 10Hz, logging every status every tick is unreadable; logging
transitions gives you one line per actual event. It reports leaves only —
composites are skipped — and ignores transitions to INVALID, which are
bookkeeping rather than behavior.

`TimerVisitor` logs how long each behavior spent RUNNING, emitting a line when
the behavior leaves the RUNNING state. It keys its bookkeeping by behavior id
rather than name, so a tree with several behaviors sharing a name still reports
correctly, and it times composites as well as leaves.

## Two things to know before using them

**Output is ANSI-colored.** `StatusTransitionVisitor` wraps each status in a
color escape. That reads well on a terminal and badly in a log file — if you
route logging to a file, expect the escapes in it.

**The logger is configurable on one but not the other.**
`StatusTransitionVisitor` accepts a `logger`, so you can route it to a named
logger of your own. `TimerVisitor` takes only a `level` and always logs to this
module's logger; to redirect it, configure the `py_branches.visitors` logger.

Both default to `logging.INFO`, so a program that has not configured logging at
all will show nothing.

## API

```{eval-rst}
.. automodule:: py_branches.visitors
   :members:
```
