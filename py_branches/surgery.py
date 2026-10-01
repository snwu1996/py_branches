#!/usr/bin/env python3
"""Changing a tree that has already been built — safely, decorators included.

A behavior tree is usually assembled once and then ticked. Sometimes it has to
be *edited* after assembly: a debug mode that replaces every real pause with
"press space to continue", a dry run that swaps every actuating leaf for a
logging stub, a subtree re-armed between runs. That edit is three lines of
recursion and one very easy mistake, which is why it lives here rather than
being rewritten in each application.

============================== ================================================
Name                           What it is
============================== ================================================
:func:`walk`                   Pre-order iteration over every node
:func:`find`                   Every node matching a predicate
:func:`find_one`               The first match, or None
:func:`find_by_name`           Every node with exactly this name
:func:`find_by_type`           Every node that is one of these types
:func:`replace`                Swap one node for another, re-parenting properly
:func:`prune`                  Detach a node from its parent
:func:`graft`                  Attach a node to a composite
:func:`swap_type`              Replace every node of some type, via a factory
:func:`dispatch`               Call something on every node satisfying a protocol
:func:`reset_subtree`          :func:`dispatch` over :class:`Resettable`
:class:`Resettable`            The protocol: ``reset()``
:class:`SurgeryError`          A structural change that cannot be made
============================== ================================================

**The mistake.** In ``py_trees``, :class:`py_trees.decorators.Decorator`
subclasses :class:`py_trees.behaviour.Behaviour`, *not*
:class:`py_trees.composites.Composite` — but it still populates
``self.children`` and aliases the child as ``self.decorated``. A walk guarded by
``if not isinstance(node, Composite): return`` therefore stops dead at every
decorator, silently, with the child sitting right there in ``.children``. Every
function here iterates ``.children`` and never asks whether a node is a
composite.

**The other half of the mistake** is the fix-up. Replacing a decorator's child
means assigning ``parent.children[i]`` *and* ``parent.decorated``; miss the
second and the decorator goes on ticking the old child forever, while the tree
renders as though the swap worked.

**What ``py_trees`` already has**, and why it is not quite enough:

* :meth:`py_trees.behaviour.Behaviour.iterate` walks ``.children`` correctly —
  but post-order, and with no search on top of it. :func:`walk` here is
  pre-order, which is the order a tree is read and drawn in.
* :meth:`py_trees.trees.BehaviourTree.replace_subtree` and its siblings are
  keyed by :class:`uuid.UUID` only, return ``bool`` instead of raising, refuse
  to touch the root, and raise a bare :exc:`RuntimeError` when the parent is a
  decorator.
* :meth:`py_trees.composites.Composite.replace_child` is correct, and
  :func:`replace` calls it. ``Decorator`` has no equivalent at all.

**Edit between ticks.** ``BehaviourTree.tick()`` builds a fresh generator from
``root.tick()`` on every tick, so there are no stale iterators to worry about;
the only live references into the old structure are ``Decorator.decorated`` and
``Composite.current_child``, and both are fixed up here. Editing a tree from
inside a running tick is not supported.

Example:
    .. testcode::

        import py_trees
        from py_branches import surgery
        from py_branches.pause import PauseUniform
        from py_branches.random import RandomRun

        # The shape that defeats a Composite-guarded walk: the pause is the
        # child of a decorator, not of a composite.
        root = py_trees.composites.Sequence(
            name="work", memory=True,
            children=[
                RandomRun(
                    child=PauseUniform(name="break", low=1.0, high=300.0),
                    name="maybe_break",
                    probability=0.1,
                ),
            ],
        )

        found = surgery.find_by_type(root, PauseUniform)
        assert [node.name for node in found] == ["break"]

        swapped = surgery.swap_type(
            root,
            PauseUniform,
            lambda old: py_trees.behaviours.Success(name=old.name),
        )
        assert swapped == 1
"""

import logging
from collections.abc import Callable
from collections.abc import Iterator
from typing import Protocol
from typing import TypeVar
from typing import runtime_checkable

import py_trees

logger = logging.getLogger(__name__)

_Behaviour = py_trees.behaviour.Behaviour
_INVALID = py_trees.common.Status.INVALID

_T = TypeVar("_T")


class SurgeryError(RuntimeError):
    """A structural change that cannot be made.

    Raised for the shapes that have no sensible answer rather than a wrong one:
    grafting onto a leaf, pruning the root, pruning the child a decorator needs,
    or attaching a node that is still attached somewhere else. Every message
    names the node and says what to do instead.
    """


@runtime_checkable
class Resettable(Protocol):
    """Anything with a ``reset()``, which :func:`reset_subtree` calls.

    A :class:`typing.Protocol`, so there is no base class to inherit — the same
    arrangement as :class:`py_branches.runtime.Closeable`.
    :class:`py_branches.latch.Latch` and :class:`py_branches.counter.Counter`
    satisfy it already, simply by having the method, and a downstream behavior
    qualifies without importing anything from here.

    ``reset()`` is about *latched state*, not about status.
    ``node.stop(INVALID)`` already ends the current round of activity; it does
    not un-latch a :class:`~py_branches.latch.Latch` or zero a
    :class:`~py_branches.counter.Counter`. That is the gap this fills.
    """

    def reset(self) -> None:
        """Re-arm whatever the object latched, so it can run again."""
        ...


# -- Traversal ----------------------------------------------------------------


def walk(
    root: _Behaviour,
    *,
    include_root: bool = True,
) -> Iterator[_Behaviour]:
    """Iterate over ``root`` and everything beneath it, parents first.

    Pre-order depth-first over ``node.children``, which every behavior has —
    composites, decorators and leaves alike. Nothing here branches on a node's
    type, which is the whole point.

    Each level is snapshotted with ``tuple()`` before it is descended into, so a
    caller may replace nodes while iterating; the walk then visits the *old*
    node's subtree, not the new one. To act on the new subtree instead, collect
    the matches first and mutate afterwards, as :func:`swap_type` does.

    Note that :meth:`py_trees.behaviour.Behaviour.iterate` is the same traversal
    in post-order (children before the node). Use that when the order matters
    the other way round; it is equally decorator-safe.

    Args:
        root (Behaviour): The node to start from.
        include_root (bool): Whether to yield ``root`` itself, keyword-only.
            Default True.

    Yields:
        Behaviour: ``root``, then each descendant in pre-order.

    Example:
        .. testcode::

            import py_trees
            from py_branches import surgery

            leaf = py_trees.behaviours.Success(name="leaf")
            root = py_trees.composites.Sequence(
                name="root", memory=True, children=[leaf]
            )
            assert [n.name for n in surgery.walk(root)] == ["root", "leaf"]
    """
    if include_root:
        yield root
    for child in tuple(root.children):
        yield from walk(child)


def find(
    root: _Behaviour,
    predicate: Callable[[_Behaviour], bool],
) -> list[_Behaviour]:
    """Collect every node beneath ``root`` for which ``predicate`` is true.

    Args:
        root (Behaviour): The node to start from; it is tested too.
        predicate (Callable[[Behaviour], bool]): The test.

    Returns:
        List[Behaviour]: Matches in pre-order. Empty if there are none.

    Example:
        .. testcode::

            import py_trees
            from py_branches import surgery

            root = py_trees.composites.Selector(
                name="root", memory=False,
                children=[py_trees.behaviours.Failure(name="nope")],
            )
            hits = surgery.find(root, lambda n: n.name.startswith("no"))
            assert [n.name for n in hits] == ["nope"]
    """
    return [node for node in walk(root) if predicate(node)]


def find_one(
    root: _Behaviour,
    predicate: Callable[[_Behaviour], bool],
) -> _Behaviour | None:
    """Return the first node matching ``predicate``, or None.

    Short-circuits, so it does not walk the rest of the tree once it has an
    answer.

    Args:
        root (Behaviour): The node to start from; it is tested too.
        predicate (Callable[[Behaviour], bool]): The test.

    Returns:
        Optional[Behaviour]: The first match in pre-order, or None.
    """
    for node in walk(root):
        if predicate(node):
            return node
    return None


def find_by_name(root: _Behaviour, name: str) -> list[_Behaviour]:
    """Collect every node named exactly ``name``.

    Exact equality, not a regular expression —
    :meth:`py_trees.behaviour.Behaviour.has_parent_with_name` matches by regex,
    and a name like ``'pause (1.5s)'`` would make that a trap.

    Names are not unique in ``py_trees``, which is why this returns a list.

    Args:
        root (Behaviour): The node to start from; it is tested too.
        name (str): The name to match.

    Returns:
        List[Behaviour]: Matches in pre-order.
    """
    return find(root, lambda node: node.name == name)


def find_by_type(root: _Behaviour, *types: type) -> list[_Behaviour]:
    """Collect every node that is an instance of any of ``types``.

    Subclasses count, as with :func:`isinstance`.

    Args:
        root (Behaviour): The node to start from; it is tested too.
        *types (type): One or more types to match.

    Returns:
        List[Behaviour]: Matches in pre-order.

    Raises:
        ValueError: If no types were given — that would match nothing, and is
            more likely a bug than a question.
    """
    if not types:
        raise ValueError("find_by_type() needs at least one type to match.")
    return find(root, lambda node: isinstance(node, types))


# -- Mutation -----------------------------------------------------------------


def replace(
    old: _Behaviour,
    new: _Behaviour,
    *,
    stop_old: bool = True,
) -> _Behaviour:
    """Put ``new`` where ``old`` is, fixing up whatever held ``old``.

    Three kinds of parent need three different fix-ups, and getting the middle
    one wrong is the defect this module exists to prevent:

    ============ ==================================================================
    ``old`` sits Fix-up
    ============ ==================================================================
    in a         :meth:`py_trees.composites.Composite.replace_child`, which also
    Composite    clears ``current_child`` if it pointed at ``old``
    under a      ``parent.children[i] = new`` **and** ``parent.decorated = new``
    Decorator    when ``decorated`` was pointing at ``old``
    at the root  Nothing to fix up. ``new`` is returned with no parent, and the
                 caller rebinds — including ``tree.root``, if it came from one
    ============ ==================================================================

    ``old`` is stopped with INVALID *before* it is detached, so its
    ``terminate()`` runs and it releases whatever it held — a keyboard listener,
    a socket, a thread. ``py_trees`` only stops a child that is RUNNING, which
    leaves a node that finished holding things nobody will ever release.

    Args:
        old (Behaviour): The node to remove. Must be in its parent's
            ``children``, which it will be unless something already corrupted
            the tree.
        new (Behaviour): The node to put in its place. Must not be attached to
            a parent.
        stop_old (bool): Whether to call ``old.stop(INVALID)`` first,
            keyword-only. Default True. It is skipped anyway when ``old`` is
            already INVALID, so a ``terminate()`` that is not idempotent is not
            run twice. Note that ``stop_old=False`` cannot fully suppress the
            stop under a composite parent:
            :meth:`py_trees.composites.Composite.remove_child` stops a RUNNING
            child itself, and that is py_trees' call to make, not this
            function's.

    Returns:
        Behaviour: ``new``, so a root replacement can be written
        ``root = surgery.replace(root, other)``.

    Raises:
        SurgeryError: If ``new`` is already attached elsewhere, or if ``old`` is
            somehow not among its own parent's children.

    Example:
        .. testcode::

            import py_trees
            from py_branches import surgery
            from py_branches.latch import Latch

            child = py_trees.behaviours.Success(name="old")
            latched = Latch(child=child, name="latch")

            fresh = py_trees.behaviours.Failure(name="new")
            surgery.replace(child, fresh)

            # Both references move, which is the part that is easy to miss.
            assert latched.children[0] is fresh
            assert latched.decorated is fresh
            assert child.parent is None
    """
    if old is new:
        return new
    if new.parent is not None:
        raise SurgeryError(
            f"replacement {new.name!r} is already a child of {new.parent.name!r}; "
            f"prune() it before grafting it somewhere else"
        )

    parent = old.parent
    if stop_old and old.status != _INVALID:
        old.stop(_INVALID)

    if parent is None:
        # Nothing holds a reference we can fix, so the caller has to rebind.
        return new

    if isinstance(parent, py_trees.composites.Composite):
        parent.replace_child(old, new)
        return new

    # A Decorator, or anything else that populates `.children` by hand. There is
    # no remove_child/replace_child to lean on, so do it directly.
    try:
        index = parent.children.index(old)
    except ValueError as error:
        raise SurgeryError(
            f"{old.name!r} names {parent.name!r} as its parent, but is not among "
            f"its children; the tree is inconsistent"
        ) from error
    parent.children[index] = new
    new.parent = parent
    # The alias, and the reason this function exists. Only move it when it was
    # actually pointing at `old` - a decorator may carry a second child that
    # `decorated` does not refer to.
    if isinstance(parent, py_trees.decorators.Decorator) and parent.decorated is old:
        parent.decorated = new
    old.parent = None
    return new


def prune(node: _Behaviour, *, stop: bool = True) -> _Behaviour:
    """Detach ``node`` from its parent and hand it back.

    As with :func:`replace`, the node is stopped with INVALID before it is
    detached, so it releases what it holds.

    Args:
        node (Behaviour): The node to detach.
        stop (bool): Whether to call ``node.stop(INVALID)`` first, keyword-only.
            Default True. Skipped when the node is already INVALID.

    Returns:
        Behaviour: ``node``, now parentless and ready to :func:`graft`
        elsewhere.

    Raises:
        SurgeryError: If ``node`` has no parent, or if it is the child a
            decorator needs in order to tick at all — use :func:`replace` for
            that.
    """
    parent = node.parent
    if parent is None:
        raise SurgeryError(
            f"{node.name!r} has no parent, so there is nothing to detach it from"
        )
    if isinstance(parent, py_trees.decorators.Decorator) and parent.decorated is node:
        raise SurgeryError(
            f"{node.name!r} is the decorated child of {parent.name!r}; a decorator "
            f"cannot tick without one. Use replace() to swap it instead"
        )

    if stop and node.status != _INVALID:
        node.stop(_INVALID)

    if isinstance(parent, py_trees.composites.Composite):
        parent.remove_child(node)
        return node
    try:
        parent.children.remove(node)
    except ValueError as error:
        raise SurgeryError(
            f"{node.name!r} names {parent.name!r} as its parent, but is not among "
            f"its children; the tree is inconsistent"
        ) from error
    node.parent = None
    return node


def graft(
    parent: _Behaviour,
    child: _Behaviour,
    index: int | None = None,
) -> _Behaviour:
    """Attach ``child`` to ``parent``, optionally at a given position.

    Only composites take new children. A decorator has exactly the one it was
    built with, and a leaf has none — ``py_trees`` would happily let a child be
    appended to either, and would then never tick it, so both are refused here.

    Args:
        parent (Composite): The composite to attach to.
        child (Behaviour): The node to attach. Must not already have a parent;
            :func:`prune` it first.
        index (Optional[int]): Position among the existing children. Default
            None, meaning append. Indices are Python list indices, so negatives
            count from the end.

    Returns:
        Behaviour: ``child``.

    Raises:
        SurgeryError: If ``child`` is still attached elsewhere, or if ``parent``
            is a decorator or a leaf.

    Example:
        .. testcode::

            import py_trees
            from py_branches import surgery

            root = py_trees.composites.Sequence(name="root", memory=True)
            first = surgery.graft(root, py_trees.behaviours.Success(name="b"))
            surgery.graft(root, py_trees.behaviours.Success(name="a"), index=0)
            assert [n.name for n in root.children] == ["a", "b"]
            assert first.parent is root
    """
    if child.parent is not None:
        raise SurgeryError(
            f"{child.name!r} is already a child of {child.parent.name!r}; "
            f"prune() it before grafting it somewhere else"
        )
    if isinstance(parent, py_trees.decorators.Decorator):
        raise SurgeryError(
            f"{parent.name!r} is a decorator and already has its child "
            f"({parent.decorated.name!r}); use replace() to swap it"
        )
    if not isinstance(parent, py_trees.composites.Composite):
        raise SurgeryError(
            f"{parent.name!r} is a leaf ({type(parent).__name__}); only a "
            f"composite can take another child"
        )

    if index is None:
        parent.add_child(child)
    else:
        parent.insert_child(child, index)
    return child


def swap_type(
    root: _Behaviour,
    types: type | tuple[type, ...],
    factory: Callable[[_Behaviour], _Behaviour],
) -> int:
    """Replace every node of the given type(s) with something ``factory`` makes.

    The generic form of the "debug mode" swap: every real pause becomes a
    keypress, every actuating leaf becomes a logging stub. ``factory`` is handed
    the node being replaced, so the replacement can keep its name and copy
    whatever else matters.

    Matches are collected before anything is replaced, so a replacement is never
    itself re-examined — a ``factory`` that returns a node of a matching type
    terminates rather than looping.

    **The root is never replaced.** Nothing here holds the reference a caller
    would need rebinding, so a matching root is skipped with a WARNING rather
    than silently counted; use :func:`replace` and rebind it yourself.

    Args:
        root (Behaviour): The node to start from.
        types (Union[type, Tuple[type, ...]]): What to match, as for
            :func:`isinstance`.
        factory (Callable[[Behaviour], Behaviour]): Called once per match with
            the node being replaced; returns its replacement.

    Returns:
        int: How many nodes were replaced. Unlike the hand-rolled version this
        replaces, the count includes nodes found under decorators — which is to
        say, it is the real count.

    Raises:
        SurgeryError: If ``factory`` returns something that is not a behavior,
            or returns a node that is already attached somewhere.

    Example:
        .. testcode::

            import py_trees
            from py_branches import surgery
            from py_branches.pause import PauseUniform
            from py_branches.random import RandomRun

            root = py_trees.composites.Sequence(
                name="root", memory=True,
                children=[
                    RandomRun(
                        child=PauseUniform(name="nap", low=1.0, high=300.0),
                        name="maybe",
                        probability=0.5,
                    ),
                ],
            )
            count = surgery.swap_type(
                root,
                PauseUniform,
                lambda old: py_trees.behaviours.Success(name=old.name),
            )
            assert count == 1
    """
    matches = [node for node in walk(root) if isinstance(node, types)]
    swapped = 0
    for old in matches:
        if old.parent is None:
            logger.warning(
                f"{old.name!r} matches but is the root, which cannot be replaced "
                f"in place; use surgery.replace() and rebind it"
            )
            continue
        new = factory(old)
        if not isinstance(new, _Behaviour):
            raise SurgeryError(
                f"the factory returned {type(new).__name__} for {old.name!r}; "
                f"it must return a py_trees Behaviour"
            )
        replace(old, new)
        swapped += 1
    logger.debug(f"swapped {swapped} node(s) under {root.name!r}")
    return swapped


# -- Protocol dispatch --------------------------------------------------------


def dispatch(
    root: _Behaviour,
    protocol: type[_T],
    action: Callable[[_T], None],
) -> int:
    """Call ``action`` on every node beneath ``root`` that satisfies ``protocol``.

    The walker, written once and parameterised, so that "reset everything that
    can be reset" and "cancel everything that can be cancelled" are one function
    with two arguments rather than two near-identical recursions.

    Args:
        root (Behaviour): The node to start from; it is tested too.
        protocol (type): A :func:`typing.runtime_checkable` protocol, or an
            ordinary class. It is used with :func:`isinstance`, so a protocol
            that is *not* runtime-checkable raises :exc:`TypeError`.
        action (Callable): Called with each matching node.

    Returns:
        int: How many nodes matched and were acted on.

    Example:
        .. testcode::

            import py_trees
            from py_branches import surgery
            from py_branches.counter import Counter

            counted = Counter(
                child=py_trees.behaviours.Success(name="work"),
                name="at_most_once",
                num_runs=1,
            )
            names = []
            found = surgery.dispatch(
                counted, surgery.Resettable, lambda n: names.append(n.name)
            )
            assert found == 1 and names == ["at_most_once"]
    """
    count = 0
    for node in walk(root):
        if isinstance(node, protocol):
            action(node)
            count += 1
    return count


def reset_subtree(root: _Behaviour) -> int:
    """Call ``reset()`` on every :class:`Resettable` node beneath ``root``.

    Re-arms latched state so a subtree can run again — a
    :class:`~py_branches.latch.Latch` un-latches, a
    :class:`~py_branches.counter.Counter` goes back to zero. Nodes without a
    ``reset()`` are left alone.

    This deliberately does **not** stop anything. ``root.stop(INVALID)`` is the
    status half of a restart and already recurses;
    :meth:`py_branches.runtime.TreeRunner.restart` calls it. Latched state is
    the half that nothing else covers, and keeping the two separate means either
    can be used without the other.

    Args:
        root (Behaviour): The node to start from; it is reset too, if it can be.

    Returns:
        int: How many nodes were reset.

    Example:
        .. testcode::

            import py_trees
            from py_branches import surgery
            from py_branches.latch import Latch

            latched = Latch(
                child=py_trees.behaviours.Success(name="work"), name="once"
            )
            latched.tick_once()
            assert surgery.reset_subtree(latched) == 1
    """
    return dispatch(root, Resettable, lambda node: node.reset())


__all__ = [
    "Resettable",
    "SurgeryError",
    "dispatch",
    "find",
    "find_by_name",
    "find_by_type",
    "find_one",
    "graft",
    "prune",
    "replace",
    "reset_subtree",
    "swap_type",
    "walk",
]
