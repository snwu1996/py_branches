# alternating

Behavior trees tick continuously, but not everything in a tree should happen on
every tick. This module covers the three shapes that need: an external switch, a
rotation between several behaviors, and a periodic or windowed gate.

## Choosing between them

`ActivateBehavior` is the primitive — a switch your application code flips. Use
it when the decision comes from outside the tree entirely (a mode change, an
operator command, a message from another process).

`run_alternating` is for round-robin work: each behavior gets a fixed run of
consecutive ticks, then the next takes over. It is built out of
`ActivateBehavior` wrappers plus a bookkeeping node, so what you get back is a
`Selector` you add to your tree like any other subtree.

`RunEveryX` and `RunEveryRange` both gate a single child, and differ in whether
the pattern is random or fixed:

| | Pattern | Use for |
|---|---|---|
| `RunEveryX` | Once every X ticks, X re-drawn from a range after each run | Polling, and anything that should not look scheduled |
| `RunEveryRange` | A fixed window of a fixed-length cycle | Phases that must line up with the same iterations every cycle |

## The `success_if_skip` flag

Every decorator here takes it, and getting it wrong is the most common mistake.
A skipped tick has to report *something*, and which status is correct depends
entirely on the composite above it:

- Under a **Selector**, leave it `False`. The skip reports FAILURE, and the
  Selector moves on to the next child — usually what you want.
- Under a **Sequence**, set it `True`. FAILURE would abort the whole sequence;
  SUCCESS makes the skip invisible and lets the following children run.

## The subtree it builds

`run_alternating` is a factory, not a decorator, so what lands in your tree is a
small subtree rather than a single node. Three behaviors cycling for 3, 2 and 4
ticks produce this:

```{figure} _static/trees/alternating_cycle.svg
:alt: A Selector containing a bookkeeping behavior followed by three ActivateBehavior decorators
:target: _static/trees/alternating_cycle.svg

`Cycle_helper` advances the rotation and always returns FAILURE, so the Selector
falls through to the `activate_*` wrappers — exactly one of which is enabled on
any given tick.
```

Two things follow from that shape. The Selector is built without memory, so it
re-evaluates from the left on every tick, which is what lets the helper run
first each time. And the behaviors you passed in are not the Selector's children
directly — each is wrapped, so a handle you kept to one of them is still the
inner behavior, not the node in the tree.

## API

```{eval-rst}
.. automodule:: py_branches.alternating
   :members:
```
