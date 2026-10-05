#!/usr/bin/env python

import os
import signal

import py_trees
import pytest

from py_branches.runtime import EXIT_SOFTWARE
from py_branches.runtime import SHUTDOWN_KEY
from py_branches.runtime import ExitBehavior
from py_branches.runtime import RaiseBehavior
from py_branches.runtime import RequestShutdown
from py_branches.runtime import RunnerState
from py_branches.runtime import ShutdownRequest
from py_branches.runtime import TreeRunner
from py_branches.runtime import clear_shutdown_request

STATUS = py_trees.common.Status


class SpyVisitor(py_trees.visitors.VisitorBase):
    """Counts how many ticks reached `finalise()`, and closes Closeably."""

    def __init__(self):
        super().__init__(full=False)
        self.finalised = 0
        self.closed = 0

    def finalise(self) -> None:
        self.finalised += 1

    def close(self) -> None:
        self.closed += 1


class SignallingBehaviour(py_trees.behaviour.Behaviour):
    """Sends `sig` to this process on the nth tick, then keeps running."""

    def __init__(self, name, sig, on_tick=1, times=1):
        super().__init__(name=name)
        self._sig = sig
        self._on_tick = on_tick
        self._times = times
        self.ticks = 0

    def update(self):
        self.ticks += 1
        if self._on_tick <= self.ticks < self._on_tick + self._times:
            os.kill(os.getpid(), self._sig)
        return STATUS.RUNNING


def pending():
    return py_trees.blackboard.Blackboard.get(SHUTDOWN_KEY)


def tree_of(behaviour):
    return py_trees.trees.BehaviourTree(behaviour)


# -- ShutdownRequest ----------------------------------------------------------


def test_shutdown_request_is_both_data_and_exception():
    request = ShutdownRequest(code=42, reason="out of ore", requested_by="miner")
    assert isinstance(request, Exception)
    assert (request.code, request.reason, request.requested_by) == (
        42,
        "out of ore",
        "miner",
    )
    assert "miner" in str(request) and "42" in str(request)


def test_shutdown_request_defaults_to_a_clean_exit():
    assert ShutdownRequest() == ShutdownRequest(code=0, reason="", requested_by="")


# -- RequestShutdown ----------------------------------------------------------


def test_request_shutdown_sets_the_key_and_returns_success():
    node = RequestShutdown(name="done", code=7, reason="finished")
    node.tick_once()
    assert node.status == STATUS.SUCCESS
    assert pending() == ShutdownRequest(code=7, reason="finished", requested_by="done")


def test_request_shutdown_can_report_failure_instead():
    node = RequestShutdown(name="give_up", status=STATUS.FAILURE)
    node.tick_once()
    assert node.status == STATUS.FAILURE
    assert pending().requested_by == "give_up"


def test_tick_completes_after_a_request():
    """The point of the whole design: the requesting tick is not abandoned."""
    root = py_trees.composites.Sequence(
        name="root",
        memory=False,
        children=[
            py_trees.behaviours.Success(name="work"),
            RequestShutdown(name="done", code=0),
        ],
    )
    tree = tree_of(root)
    spy = SpyVisitor()
    tree.visitors.append(spy)

    runner = TreeRunner(tree, rate=None, max_ticks=5, signals=())
    assert runner.run() == 0
    assert runner.ticks == 1
    # Visitors finalised and the tick was counted, both of which a mid-tick
    # sys.exit() would have skipped.
    assert spy.finalised == 1
    assert tree.count == 1
    assert spy.closed == 1


@pytest.mark.parametrize("code", [0, 1, 42])
def test_runner_exits_with_the_requested_code(code):
    tree = tree_of(RequestShutdown(name="done", code=code))
    runner = TreeRunner(tree, rate=None, max_ticks=5, signals=())
    assert runner.run() == code
    assert runner.ticks == 1


def test_first_request_wins():
    root = py_trees.composites.Sequence(
        name="root",
        memory=False,
        children=[
            RequestShutdown(name="first", code=11),
            RequestShutdown(name="second", code=22),
        ],
    )
    runner = TreeRunner(tree_of(root), rate=None, max_ticks=5, signals=())
    assert runner.run() == 11


def test_request_without_a_runner_is_inert():
    node = RequestShutdown(name="done", code=5)
    for _ in range(3):
        node.tick_once()
    assert node.status == STATUS.SUCCESS
    assert pending().code == 5


def test_a_foreign_value_on_the_key_is_ignored():
    client = py_trees.blackboard.Client(name="intruder")
    client.register_key(key=SHUTDOWN_KEY, access=py_trees.common.Access.WRITE)
    client.set(SHUTDOWN_KEY, "not a request")

    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")),
        rate=None,
        max_ticks=3,
        signals=(),
    )
    assert runner.run() == 0
    assert runner.ticks == 3


def test_clear_shutdown_request_is_safe_when_nothing_is_pending():
    clear_shutdown_request()
    clear_shutdown_request()
    assert not py_trees.blackboard.Blackboard.exists(SHUTDOWN_KEY)


def test_restart_clears_a_pending_request():
    runner = TreeRunner(
        tree_of(RequestShutdown(name="done", code=3)),
        rate=None,
        max_ticks=5,
        signals=(),
    )
    assert runner.run() == 3
    assert py_trees.blackboard.Blackboard.exists(SHUTDOWN_KEY)

    runner.restart()
    assert not py_trees.blackboard.Blackboard.exists(SHUTDOWN_KEY)


# -- ExitBehavior -------------------------------------------------------------


def test_exit_behavior_is_backwards_compatible_with_legacy_callers():
    """Existing callers build it as `ExitBehavior(name='exit_worker')` and tick it."""
    node = ExitBehavior(name="exit_worker")
    node.tick_once()
    assert node.status == STATUS.SUCCESS
    assert pending() == ShutdownRequest(code=0, reason="", requested_by="exit_worker")


def test_exit_behavior_defaults_its_name():
    assert ExitBehavior().name == "exit"


def test_request_is_readable_before_ticking():
    node = RequestShutdown(name="done", code=4, reason="quota met")
    assert node.request == ShutdownRequest(
        code=4, reason="quota met", requested_by="done"
    )
    assert not py_trees.blackboard.Blackboard.exists(SHUTDOWN_KEY)


def test_immediate_raises_and_the_runner_catches_it():
    tree = tree_of(ExitBehavior(name="bail", code=9, immediate=True))
    spy = SpyVisitor()
    tree.visitors.append(spy)

    runner = TreeRunner(tree, rate=None, max_ticks=5, signals=())
    assert runner.run() == 9
    # Teardown still ran...
    assert spy.closed == 1
    assert runner.state is RunnerState.STOPPED
    # ...but this is what immediate costs: the tick never finalised, and the
    # tree never counted it.
    assert spy.finalised == 0
    assert tree.count == 0
    assert not py_trees.blackboard.Blackboard.exists(SHUTDOWN_KEY)


# -- RaiseBehavior ------------------------------------------------------------


def test_raise_behavior_propagates_after_teardown():
    tree = tree_of(RaiseBehavior(name="impossible", exception=ValueError("nope")))
    spy = SpyVisitor()
    tree.visitors.append(spy)

    runner = TreeRunner(tree, rate=None, max_ticks=5, signals=())
    with pytest.raises(ValueError, match="nope"):
        runner.run()

    assert spy.closed == 1
    assert runner.exit_code == EXIT_SOFTWARE


def test_raise_behavior_accepts_a_class_an_instance_or_a_factory():
    for exception in (
        KeyError,
        KeyError("instance"),
        lambda: KeyError("factory"),
    ):
        node = RaiseBehavior(name="boom", exception=exception)
        with pytest.raises(KeyError):
            node.tick_once()


# -- Signals ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sig", "code"),
    [(signal.SIGINT, 130), (signal.SIGTERM, 143)],
)
def test_a_signal_synthesizes_the_same_shutdown(sig, code):
    before = signal.getsignal(sig)
    tree = tree_of(SignallingBehaviour(name="noisy", sig=sig, on_tick=1))
    # max_ticks bounds the test so a failure cannot hang CI.
    runner = TreeRunner(tree, rate=None, max_ticks=50, signals=(sig,))
    assert runner.run() == code
    # The tick in flight when the signal landed still completed.
    assert runner.ticks >= 1
    assert signal.getsignal(sig) is before


def test_second_signal_forces_exit_through_a_hung_teardown():
    class HangingVisitor(py_trees.visitors.VisitorBase):
        """Stands in for a close() stuck on a socket, by signalling again."""

        def close(self) -> None:
            os.kill(os.getpid(), signal.SIGINT)

    tree = tree_of(SignallingBehaviour(name="noisy", sig=signal.SIGINT, on_tick=1))
    tree.visitors.append(HangingVisitor())
    runner = TreeRunner(tree, rate=None, max_ticks=50, signals=(signal.SIGINT,))

    # The first SIGINT asks nicely; the second, raised from inside teardown,
    # restores the default handler and escapes as a KeyboardInterrupt.
    with pytest.raises(KeyboardInterrupt):
        runner.run()
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


def test_keyboard_interrupt_without_a_handler_still_reports_130():
    class InterruptingBehaviour(py_trees.behaviour.Behaviour):
        def update(self):
            raise KeyboardInterrupt

    runner = TreeRunner(
        tree_of(InterruptingBehaviour(name="ctrl_c")),
        rate=None,
        max_ticks=5,
        signals=(),
    )
    assert runner.run() == 130
