# latch

`Latch` passes its child's status through until the child returns SUCCESS once,
after which it reports SUCCESS forever without ticking the child again. Use it
for setup that must succeed before the rest of the tree is meaningful.

## Only SUCCESS latches

A child that returns FAILURE does not engage the latch; it will be ticked again
on the next tick. This is the useful property — a `Latch` around a flaky setup
step keeps retrying it every tick until it works, then never again.

If you want to bound those retries, wrap the child in {doc}`retry`'s `Retry`
first, or use {doc}`counter`'s `Counter`, which stops after a set number of
attempts whether or not they succeeded.

## State outlives the tree

Like `Counter`, the latch is deliberately *not* cleared by `initialise()`, so
re-entering the subtree does not unlatch it. Call `reset()` to do that
explicitly — typically from application code that knows the setup has been
invalidated.

## API

```{eval-rst}
.. automodule:: py_branches.latch
   :members:
```
