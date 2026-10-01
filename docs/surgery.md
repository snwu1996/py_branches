# surgery

`surgery` edits a behavior tree that has already been built — find a node, swap
it, detach it, attach another one — and gets the re-parenting right for every
kind of parent, including the one that is easy to get wrong.

A tree is usually assembled once and then ticked. Sometimes it has to be
changed afterwards: a debug mode that replaces every real pause with "press
space to continue", a dry run that swaps every actuating leaf for a logging
stub, a subtree re-armed between runs. That is three lines of recursion and one
very easy mistake.

## The mistake

In py_trees, `Decorator` subclasses `Behaviour`, **not** `Composite`. But it
still populates `self.children`, and aliases the child as `self.decorated`:

```python
# py_trees/decorators.py
super().__init__(name=name)
self.children.append(child)
self.decorated = self.children[0]
self.decorated.parent = self
```

So the obvious walk —

```python
def swap(root):
    if not isinstance(root, Composite):  # ← stops dead at every decorator
        return 0
    for i, child in enumerate(list(root.children)):
        ...
```

— never descends past a decorator, even though the child is sitting right there
in `.children`. It returns a count, that count is short, and nothing says so.
In practice that means a tree like

```python
RandomRun(child=PauseUniform(name="random_break", low=1, high=300), probability=0.1)
```

still pauses for up to five real minutes in a debug run that was supposed to
have removed every pause.

Every function here iterates `.children` and never asks whether a node is a
composite.

## The other half of the mistake

Replacing a decorator's child means fixing up **two** references:

| `old.parent` | Fix-up |
|---|---|
| `Composite` | `parent.children[i] = new`, `new.parent = parent` — and clear `current_child` if it pointed at `old` |
| `Decorator` | `parent.children[i] = new`, `new.parent = parent`, **and `parent.decorated = new`** |
| `None` (root) | Nothing to fix up; `replace()` returns the new node and the caller rebinds |

Miss `parent.decorated` and the decorator goes on ticking the old child
forever, while `unicode_tree()` renders the new one. `replace()` does all
three, and stops the outgoing node with `INVALID` first so its `terminate()`
runs and it releases whatever it held.

## What py_trees already gives you

| Already provided | py_trees API | Why it is not enough here |
|---|---|---|
| Decorator-safe traversal | `Behaviour.iterate()` | Post-order only, and no search on top |
| Subtree replace / prune / insert | `BehaviourTree.replace_subtree` etc. | Keyed by `uuid.UUID` only, return `bool` instead of raising, refuse to touch the root, and raise a bare `RuntimeError` for a decorator parent |
| Child replacement in a composite | `Composite.replace_child` | Correct — `replace()` calls it. `Decorator` has no equivalent |
| Ancestor search | `has_parent_with_name`, `has_parent_with_instance_type` | The inverse of what is wanted |
| Rendering | `display.unicode_tree`, `display.dot_tree` | Walks correctly, but does not search |

`walk()` differs from `iterate()` in one respect only: it is pre-order, the
order a tree is read and drawn in. `iterate()` is not broken; it answers a
different question.

## Edit between ticks

`BehaviourTree.tick()` builds a fresh generator from `root.tick()` on every
tick, so there are no stale iterators to worry about. The only live references
into the old structure are `Decorator.decorated` and `Composite.current_child`,
and both are fixed up here. Editing a tree from inside a running tick is not
supported.

## Finding nodes

```python
from py_branches import surgery

surgery.walk(root)  # every node, parents first
surgery.find(root, lambda n: n.status == FAILURE)  # predicate
surgery.find_one(root, lambda n: n.name == "x")  # first match, or None
surgery.find_by_name(root, "random_break_pause")  # exact, not regex
surgery.find_by_type(root, PauseUniform, PausePDF)
```

`find_by_name` matches exactly. py_trees' own `has_parent_with_name` is a regex
match, which turns a name like `pause (1.5s)` into a trap.

## Changing them

```python
surgery.replace(old, new)  # returns new; rebind if old was the root
surgery.prune(node)  # returns the detached node
surgery.graft(parent, child, index=None)  # composites only
surgery.swap_type(
    root,
    (PauseUniform, PausePDF),
    lambda old: PauseUntilKey(name=old.name, key="space"),
)
```

`swap_type` collects its matches before it changes anything, so a factory that
returns a node of a matching type terminates instead of looping. It never
replaces the root — nothing here holds the reference a caller would have to
rebind — and warns rather than silently counting it.

The refusals are deliberate. `graft` onto a leaf or a decorator raises
`SurgeryError`, because py_trees would accept the child and then never tick it.
`prune` on the child a decorator needs raises too: use `replace`.

## Resetting

```python
surgery.reset_subtree(root)  # every node with a reset()
surgery.dispatch(root, surgery.Resettable, lambda n: n.reset())
```

`Resettable` is a `runtime_checkable` Protocol with one method, `reset()`, in
the same style as `runtime.Closeable` — there is no base class to inherit, and
`Latch` and `Counter` satisfy it already.

`reset()` is about *latched state*, not status. `node.stop(INVALID)` already
ends the current round of activity and recurses; it does not un-latch a `Latch`
or zero a `Counter`. `reset_subtree` covers that half and deliberately changes
no statuses, so either can be used without the other.

`dispatch` is the walker written once and parameterised by protocol, so "reset
everything that can be reset" and "cancel everything that can be cancelled" are
one function with two arguments rather than two near-identical recursions.

## API

```{eval-rst}
.. automodule:: py_branches.surgery
   :members:
```
