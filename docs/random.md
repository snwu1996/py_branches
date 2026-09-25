# random

Two decorators and a factory for behavior that should not be fully
deterministic — either because the real thing being modelled is not, or because
several agents sharing a tree need to stop moving in lockstep.

## Choosing between them

`RandomRun` decides *whether* the child runs; `RandomDelay` always runs it, but
decides *when*. They compose: wrapping a `RandomRun` in a `RandomDelay` gives a
child that sometimes runs, and when it does, not immediately.

`random_selector` picks exactly one behavior from a weighted set. Reach for it
when the weights are the point — a behavior profile, say, where an agent idles
50% of the time, patrols 30%, and investigates 20%.

## Why the weights are rewritten

`random_selector` does something non-obvious worth understanding before you
debug it. A py_trees `Selector` tries children left to right and stops at the
first SUCCESS, so the second child is only reached when the first was skipped.
Passing your weights through directly would therefore under-select every child
after the first.

The factory converts your **absolute** weights into the **conditional**
probabilities that produce them. Given `[0.2, 0.3, 0.5]`, the wrapper on the
second child is built with `0.375`, not `0.3`. If you inspect the tree and find
probabilities that do not match what you passed in, this is why — and the last
child is often undecorated entirely, because by the time the selector reaches
it, it must run.

The rewriting is visible in the tree itself:

```{figure} _static/trees/weighted_selection.svg
:alt: A Selector with two RandomRun decorators and one undecorated behavior
:target: _static/trees/weighted_selection.svg

Weights of 20%, 30% and 50%. `Idle` and `Patrol` are wrapped in `RandomRun`
decorators carrying conditional probabilities, while `Investigate` is added
undecorated — once the first two are skipped, it must run.
```

One consequence: order matters. The same weights in a different order produce
the same selection frequencies, but the tree they build is not identical.

## API

```{eval-rst}
.. automodule:: py_branches.random
   :members:
```
