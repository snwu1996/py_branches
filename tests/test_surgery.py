#!/usr/bin/env python

import py_trees
import pytest

from py_branches import surgery
from py_branches.counter import Counter
from py_branches.latch import Latch
from py_branches.pause import PauseUniform
from py_branches.pause import PauseUntilKey
from py_branches.random import RandomRun
from py_branches.surgery import SurgeryError

STATUS = py_trees.common.Status


class RecordingBehaviour(py_trees.behaviour.Behaviour):
    """Appends its name to a shared log on every tick and every terminate."""

    def __init__(self, name, log, status=STATUS.SUCCESS):
        super().__init__(name=name)
        self.log = log
        self._status = status

    def update(self):
        self.log.append(f"tick:{self.name}")
        return self._status

    def terminate(self, new_status):
        self.log.append(f"terminate:{self.name}:{new_status.name}")


class TwoChildDecorator(py_trees.decorators.Decorator):
    """A decorator carrying a second child that ``decorated`` does not name.

    The shape the Interrupt design calls for: a watcher living at
    ``children[1]``. Generic walkers see it; ``decorated`` must not follow it.
    """

    def __init__(self, name, child, watcher):
        super().__init__(name=name, child=child)
        self.children.append(watcher)
        watcher.parent = self

    def update(self):
        return self.decorated.status


def noop(name):
    return py_trees.behaviours.Success(name=name)


def sequence(name, children):
    return py_trees.composites.Sequence(name=name, memory=True, children=children)


def pause_uniform(name="pause"):
    return PauseUniform(name=name, low=0.01, high=0.02)


def to_until_key(old):
    return PauseUntilKey(name=old.name, key="space")


# -- walk ---------------------------------------------------------------------


def test_walk_is_pre_order():
    inner = sequence("inner", [noop("a"), noop("b")])
    root = sequence("root", [inner, noop("c")])
    assert [n.name for n in surgery.walk(root)] == [
        "root",
        "inner",
        "a",
        "b",
        "c",
    ]


def test_walk_descends_into_decorators():
    # The defect in one assertion: a Decorator is not a Composite, but its
    # child is right there in .children.
    decorated = RandomRun(child=noop("hidden"), name="maybe", probability=0.5)
    root = sequence("root", [decorated])
    assert "hidden" in [n.name for n in surgery.walk(root)]


def test_walk_descends_into_nested_decorators():
    deep = Latch(
        child=RandomRun(child=noop("deep"), name="maybe", probability=0.5), name="latch"
    )
    assert [n.name for n in surgery.walk(deep)] == ["latch", "maybe", "deep"]


def test_walk_can_skip_the_root():
    root = sequence("root", [noop("a")])
    assert [n.name for n in surgery.walk(root, include_root=False)] == ["a"]


def test_walk_on_a_leaf_yields_only_the_leaf():
    assert [n.name for n in surgery.walk(noop("solo"))] == ["solo"]


# -- find ---------------------------------------------------------------------


def test_find_returns_matches_in_pre_order():
    root = sequence("root", [noop("keep_a"), sequence("mid", [noop("keep_b")])])
    hits = surgery.find(root, lambda n: n.name.startswith("keep"))
    assert [n.name for n in hits] == ["keep_a", "keep_b"]


def test_find_one_returns_the_first_match_or_none():
    root = sequence("root", [noop("a"), noop("a")])
    first = surgery.find_one(root, lambda n: n.name == "a")
    assert first is root.children[0]
    assert surgery.find_one(root, lambda n: n.name == "zzz") is None


def test_find_by_name_is_exact_not_regex():
    root = sequence("root", [noop("pause (1.5s)"), noop("pause")])
    assert [n.name for n in surgery.find_by_name(root, "pause")] == ["pause"]


def test_find_by_name_returns_every_duplicate():
    root = sequence("root", [noop("dup"), sequence("mid", [noop("dup")])])
    assert len(surgery.find_by_name(root, "dup")) == 2


def test_find_by_type_matches_several_types_and_sees_through_decorators():
    root = sequence(
        "root",
        [
            RandomRun(
                child=pause_uniform("under_decorator"), name="maybe", probability=0.5
            ),
            PauseUntilKey(name="already_a_key_pause", key="space"),
        ],
    )
    hits = surgery.find_by_type(root, PauseUniform, PauseUntilKey)
    assert [n.name for n in hits] == ["under_decorator", "already_a_key_pause"]


def test_find_by_type_without_types_is_an_error():
    with pytest.raises(ValueError, match="at least one type"):
        surgery.find_by_type(noop("solo"))


# -- replace ------------------------------------------------------------------


def test_replace_under_a_composite_keeps_the_index_and_reparents():
    old = noop("old")
    root = sequence("root", [noop("before"), old, noop("after")])
    new = noop("new")

    assert surgery.replace(old, new) is new
    assert [n.name for n in root.children] == ["before", "new", "after"]
    assert new.parent is root
    assert old.parent is None


def test_replace_under_a_decorator_rebinds_decorated():
    old = noop("old")
    decorated = RandomRun(child=old, name="maybe", probability=1.0)
    new = noop("new")

    surgery.replace(old, new)

    assert decorated.children[0] is new
    assert decorated.decorated is new
    assert new.parent is decorated
    assert old.parent is None


def test_replaced_decorator_child_is_the_one_that_ticks():
    # The assertion that would have caught the original bug at the call site: a
    # decorator that kept `decorated` pointing at the old child goes on
    # ticking it, however good the tree renders.
    log = []
    old = RecordingBehaviour("old", log)
    decorated = RandomRun(child=old, name="always", probability=1.0)
    new = RecordingBehaviour("new", log)

    surgery.replace(old, new)
    log.clear()
    decorated.tick_once()

    assert "tick:new" in log
    assert "tick:old" not in log


def test_replace_leaves_a_second_decorator_child_alone():
    watched = noop("watched")
    watcher = noop("watcher")
    decorated = TwoChildDecorator("guarded", child=watched, watcher=watcher)
    new = noop("new_watcher")

    surgery.replace(watcher, new)

    assert decorated.children[1] is new
    assert decorated.decorated is watched, "decorated must not follow children[1]"


def test_replace_at_the_root_returns_the_new_node_for_rebinding():
    old = sequence("old_root", [noop("a")])
    new = sequence("new_root", [])

    result = surgery.replace(old, new)

    assert result is new
    assert new.parent is None


def test_replace_stops_the_old_node_so_it_terminates():
    log = []
    old = RecordingBehaviour("old", log, status=STATUS.RUNNING)
    root = sequence("root", [old])
    root.tick_once()
    log.clear()

    surgery.replace(old, noop("new"))

    assert log == ["terminate:old:INVALID"]
    assert old.status == STATUS.INVALID


def test_replace_does_not_terminate_a_node_that_is_already_invalid():
    log = []
    old = RecordingBehaviour("old", log)
    root = sequence("root", [old])
    old.stop(STATUS.INVALID)
    log.clear()

    surgery.replace(old, noop("new"))

    assert log == []
    assert root.children[0].name == "new"


def test_replace_can_be_told_not_to_stop_the_old_node():
    log = []
    old = RecordingBehaviour("old", log, status=STATUS.RUNNING)
    decorated = RandomRun(child=old, name="always", probability=1.0)
    decorated.tick_once()
    log.clear()

    surgery.replace(old, noop("new"), stop_old=False)

    assert log == []
    assert old.status == STATUS.RUNNING


def test_stop_old_false_cannot_suppress_a_composites_own_stop():
    # py_trees' Composite.remove_child stops a RUNNING child itself. Documented
    # rather than worked around: that is py_trees' call to make.
    log = []
    old = RecordingBehaviour("old", log, status=STATUS.RUNNING)
    root = sequence("root", [old])
    root.tick_once()
    log.clear()

    surgery.replace(old, noop("new"), stop_old=False)

    assert log == ["terminate:old:INVALID"]


def test_replace_clears_current_child_when_it_was_the_replaced_node():
    old = py_trees.behaviours.Running(name="old")
    root = sequence("root", [old])
    root.tick_once()
    assert root.current_child is old

    surgery.replace(old, noop("new"))

    assert root.current_child is not old


def test_replace_rejects_a_replacement_that_is_still_attached():
    old = noop("old")
    root = sequence("root", [old, noop("taken")])

    with pytest.raises(SurgeryError, match="already a child"):
        surgery.replace(old, root.children[1])


def test_replace_with_itself_is_a_noop():
    node = noop("node")
    root = sequence("root", [node])
    assert surgery.replace(node, node) is node
    assert root.children == [node]


# -- prune / graft ------------------------------------------------------------


def test_prune_detaches_and_returns_the_node():
    node = noop("node")
    root = sequence("root", [noop("a"), node])

    assert surgery.prune(node) is node
    assert [n.name for n in root.children] == ["a"]
    assert node.parent is None


def test_prune_stops_the_node():
    log = []
    node = RecordingBehaviour("node", log, status=STATUS.RUNNING)
    root = sequence("root", [node])
    root.tick_once()
    log.clear()

    surgery.prune(node)

    assert log == ["terminate:node:INVALID"]


def test_prune_without_a_parent_is_an_error():
    with pytest.raises(SurgeryError, match="no parent"):
        surgery.prune(noop("solo"))


def test_prune_refuses_the_child_a_decorator_needs():
    child = noop("child")
    RandomRun(child=child, name="maybe", probability=0.5)

    with pytest.raises(SurgeryError, match="decorated child"):
        surgery.prune(child)


def test_prune_allows_a_decorators_second_child():
    watcher = noop("watcher")
    decorated = TwoChildDecorator("guarded", child=noop("watched"), watcher=watcher)

    surgery.prune(watcher)

    assert decorated.children == [decorated.decorated]
    assert watcher.parent is None


def test_graft_appends_by_default_and_inserts_at_an_index():
    root = sequence("root", [])
    surgery.graft(root, noop("b"))
    surgery.graft(root, noop("a"), index=0)
    assert [n.name for n in root.children] == ["a", "b"]
    assert all(child.parent is root for child in root.children)


def test_prune_then_graft_round_trips():
    node = noop("node")
    source = sequence("source", [node])
    target = sequence("target", [])

    surgery.graft(target, surgery.prune(node))

    assert source.children == []
    assert target.children == [node]
    assert node.parent is target


def test_graft_rejects_a_still_attached_child():
    node = noop("node")
    sequence("source", [node])
    target = sequence("target", [])

    with pytest.raises(SurgeryError, match="already a child"):
        surgery.graft(target, node)


def test_graft_onto_a_decorator_is_an_error():
    decorated = RandomRun(child=noop("child"), name="maybe", probability=0.5)

    with pytest.raises(SurgeryError, match="already has its child"):
        surgery.graft(decorated, noop("extra"))


def test_graft_onto_a_leaf_is_an_error():
    with pytest.raises(SurgeryError, match="is a leaf"):
        surgery.graft(noop("leaf"), noop("extra"))


# -- swap_type ----------------------------------------------------------------
#
# The first six port the regression baseline this module replaces; the rest are
# what that baseline missed.


def test_swap_replaces_every_matching_leaf():
    root = sequence("root", [noop("noop"), pause_uniform("p1"), pause_uniform("p2")])

    assert surgery.swap_type(root, (PauseUniform,), to_until_key) == 2
    assert [type(n).__name__ for n in root.children] == [
        "Success",
        "PauseUntilKey",
        "PauseUntilKey",
    ]


def test_swap_recurses_into_nested_composites():
    inner = sequence("inner", [pause_uniform("inner_pause")])
    root = py_trees.composites.Selector(
        name="root", memory=False, children=[inner, pause_uniform("outer_pause")]
    )

    assert surgery.swap_type(root, (PauseUniform,), to_until_key) == 2
    assert isinstance(inner.children[0], PauseUntilKey)
    assert isinstance(root.children[1], PauseUntilKey)


def test_swap_preserves_names_and_parent_links():
    inner = sequence("inner", [pause_uniform("inner_pause")])
    root = sequence("root", [inner, pause_uniform("outer_pause")])

    surgery.swap_type(root, (PauseUniform,), to_until_key)

    assert inner.children[0].name == "inner_pause"
    assert inner.children[0].parent is inner
    assert root.children[1].name == "outer_pause"
    assert root.children[1].parent is root


def test_swap_returns_zero_when_nothing_matches():
    root = sequence("root", [noop("a"), sequence("inner", [noop("b")])])
    assert surgery.swap_type(root, (PauseUniform,), to_until_key) == 0


def test_swap_on_a_leaf_root_is_a_noop():
    assert surgery.swap_type(noop("solo"), (PauseUniform,), to_until_key) == 0


def test_swap_accepts_a_bare_type_as_well_as_a_tuple():
    root = sequence("root", [pause_uniform("p")])
    assert surgery.swap_type(root, PauseUniform, to_until_key) == 1


def test_swap_reaches_a_pause_inside_a_decorator():
    # The defect. The earlier Composite-guarded walk returns 0 here and logs
    # it as success, leaving a real 300-second pause in a debug run.
    decorated = RandomRun(
        child=PauseUniform(name="random_break_pause", low=1.0, high=300.0),
        name="random_break",
        probability=0.5,
    )
    root = sequence("root", [decorated])

    assert surgery.swap_type(root, (PauseUniform,), to_until_key) == 1
    assert isinstance(decorated.decorated, PauseUntilKey)
    assert decorated.children[0] is decorated.decorated
    assert decorated.decorated.name == "random_break_pause"


def test_swap_reaches_a_pause_under_a_composite_under_a_decorator():
    inner = sequence("inner", [pause_uniform("buried")])
    decorated = Latch(child=inner, name="latch")
    root = sequence("root", [decorated])

    assert surgery.swap_type(root, (PauseUniform,), to_until_key) == 1
    assert isinstance(inner.children[0], PauseUntilKey)


def test_swap_reaches_a_pause_under_nested_decorators():
    decorated = Latch(
        child=RandomRun(child=pause_uniform("buried"), name="maybe", probability=0.5),
        name="latch",
    )

    assert surgery.swap_type(decorated, (PauseUniform,), to_until_key) == 1
    inner = decorated.decorated
    assert isinstance(inner, RandomRun)
    assert isinstance(inner.decorated, PauseUntilKey)


def test_swap_passes_the_replaced_node_to_the_factory():
    seen = []

    def factory(old):
        seen.append(old)
        return to_until_key(old)

    root = sequence("root", [pause_uniform("p")])
    original = root.children[0]

    surgery.swap_type(root, (PauseUniform,), factory)

    assert seen == [original]


def test_swap_does_not_re_examine_its_own_replacements():
    # A factory returning a matching type would loop if matches were collected
    # lazily. It terminates, and each node is replaced exactly once.
    calls = []

    def factory(old):
        calls.append(old.name)
        return pause_uniform(old.name)

    root = sequence("root", [pause_uniform("a"), pause_uniform("b")])
    assert surgery.swap_type(root, (PauseUniform,), factory) == 2
    assert calls == ["a", "b"]


def test_swap_skips_a_matching_root_and_warns(caplog):
    root = pause_uniform("root_pause")

    with caplog.at_level("WARNING", logger="py_branches.surgery"):
        assert surgery.swap_type(root, (PauseUniform,), to_until_key) == 0

    assert "cannot be replaced in place" in caplog.text


def test_swap_rejects_a_factory_that_returns_a_non_behaviour():
    root = sequence("root", [pause_uniform("p")])

    def bad_factory(old):
        return "not a behaviour"

    with pytest.raises(SurgeryError, match="must return a py_trees Behaviour"):
        surgery.swap_type(root, (PauseUniform,), bad_factory)  # type: ignore[arg-type]


def test_swap_stops_the_nodes_it_replaces():
    log = []
    old = RecordingBehaviour("old", log, status=STATUS.RUNNING)
    root = sequence("root", [old])
    root.tick_once()
    log.clear()

    surgery.swap_type(root, RecordingBehaviour, lambda n: noop(n.name))

    assert log == ["terminate:old:INVALID"]


def test_swap_leaves_the_rendered_tree_shaped_the_same():
    def build():
        return sequence(
            "root",
            [
                RandomRun(child=pause_uniform("nap"), name="maybe", probability=0.5),
                noop("work"),
            ],
        )

    before = py_trees.display.unicode_tree(build())
    after_root = build()
    surgery.swap_type(after_root, (PauseUniform,), to_until_key)
    after = py_trees.display.unicode_tree(after_root)

    # Same shape, same names, same indentation - only the node changed.
    assert [line.rstrip() for line in before.splitlines()] == [
        line.rstrip() for line in after.splitlines()
    ]


# -- dispatch / reset_subtree -------------------------------------------------


def test_dispatch_calls_the_action_on_every_matching_node():
    seen = []
    root = sequence(
        "root",
        [
            Latch(child=noop("a"), name="latch"),
            noop("plain"),
            Counter(child=noop("b"), name="counter", num_runs=1),
        ],
    )

    def record(node):
        seen.append(node.name)

    count = surgery.dispatch(root, surgery.Resettable, record)

    assert count == 2
    assert seen == ["latch", "counter"]


def test_resettable_recognises_the_packages_own_decorators():
    assert isinstance(Latch(child=noop("a"), name="latch"), surgery.Resettable)
    assert isinstance(
        Counter(child=noop("b"), name="counter", num_runs=1), surgery.Resettable
    )
    assert not isinstance(noop("plain"), surgery.Resettable)


def test_reset_subtree_re_arms_a_latch_so_the_child_runs_again():
    log = []
    child = RecordingBehaviour("work", log)
    latched = Latch(child=child, name="latch")

    latched.tick_once()
    log.clear()
    latched.tick_once()
    assert log == [], "latched: the child should not have run"

    assert surgery.reset_subtree(latched) == 1
    latched.tick_once()
    assert "tick:work" in log


def test_reset_subtree_re_arms_a_counter():
    log = []
    counted = Counter(child=RecordingBehaviour("work", log), name="counter", num_runs=1)

    counted.tick_once()
    log.clear()
    counted.tick_once()
    assert log == [], "capped: the child should not have run"

    assert surgery.reset_subtree(counted) == 1
    counted.tick_once()
    assert "tick:work" in log


def test_reset_subtree_reaches_nodes_under_decorators():
    inner = Counter(child=noop("work"), name="counter", num_runs=1)
    root = sequence("root", [Latch(child=inner, name="latch")])

    assert surgery.reset_subtree(root) == 2


def test_reset_subtree_does_not_change_status():
    counted = Counter(child=noop("work"), name="counter", num_runs=1)
    counted.tick_once()
    before = counted.status

    surgery.reset_subtree(counted)

    assert counted.status == before


def test_reset_subtree_returns_zero_when_nothing_is_resettable():
    assert surgery.reset_subtree(sequence("root", [noop("a")])) == 0
