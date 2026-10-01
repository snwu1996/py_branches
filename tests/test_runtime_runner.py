#!/usr/bin/env python

import signal
import threading
import time

import py_trees
import pytest

from py_branches.clock import ManualClock
from py_branches.runtime import EXIT_FAILURE
from py_branches.runtime import EXIT_OK
from py_branches.runtime import EXIT_SETUP_FAILED
from py_branches.runtime import EXIT_SOFTWARE
from py_branches.runtime import Closeable
from py_branches.runtime import RaiseBehavior
from py_branches.runtime import RunnerState
from py_branches.runtime import SetupError
from py_branches.runtime import TreeRunner

STATUS = py_trees.common.Status


class RecordingClock(ManualClock):
    """A ManualClock that remembers every sleep it was asked for."""

    def __init__(self, start: float = 0.0):
        super().__init__(start)
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        super().sleep(seconds)


class SlowBehaviour(py_trees.behaviour.Behaviour):
    """Costs `duration` clock-seconds per tick, without costing real time."""

    def __init__(self, name, clock, duration, status=STATUS.SUCCESS):
        super().__init__(name=name)
        self._clock = clock
        self._duration = duration
        self._status = status

    def update(self):
        self._clock.advance(self._duration)
        return self._status


class RecordingBehaviour(py_trees.behaviour.Behaviour):
    """Appends its lifecycle events to a shared log."""

    def __init__(self, name, log, status=STATUS.RUNNING):
        super().__init__(name=name)
        self._log = log
        self._status = status

    def update(self):
        return self._status

    def terminate(self, new_status):
        self._log.append("terminate")

    def shutdown(self):
        self._log.append("shutdown")


class RecordingVisitor(py_trees.visitors.VisitorBase):
    """A Closeable visitor that records its close, or raises on it."""

    def __init__(self, log, label="close", raises=False):
        super().__init__(full=False)
        self._log = log
        self._label = label
        self._raises = raises

    def close(self) -> None:
        self._log.append(self._label)
        if self._raises:
            raise RuntimeError(f"{self._label} failed")


class SpanBehaviour(py_trees.behaviour.Behaviour):
    """Records a marker on entering and leaving every tick."""

    def __init__(self, name, log):
        super().__init__(name=name)
        self._log = log

    def update(self):
        self._log.append("enter")
        self._log.append("leave")
        return STATUS.RUNNING


def tree_of(behaviour: py_trees.behaviour.Behaviour) -> py_trees.trees.BehaviourTree:
    return py_trees.trees.BehaviourTree(behaviour)


def run_in_thread(runner: TreeRunner) -> threading.Thread:
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    return thread


# -- The loop -----------------------------------------------------------------


def test_runs_until_max_ticks():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")),
        rate=None,
        max_ticks=4,
        signals=(),
    )
    assert runner.run() == EXIT_OK
    assert runner.ticks == 4
    assert runner.state is RunnerState.STOPPED


def test_stop_on_success():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Success(name="done")),
        rate=None,
        max_ticks=10,
        stop_on=(STATUS.SUCCESS, STATUS.FAILURE),
        signals=(),
    )
    assert runner.run() == EXIT_OK
    assert runner.ticks == 1


def test_stop_on_failure():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Failure(name="nope")),
        rate=None,
        max_ticks=10,
        stop_on=(STATUS.SUCCESS, STATUS.FAILURE),
        signals=(),
    )
    assert runner.run() == EXIT_FAILURE
    assert runner.ticks == 1


def test_empty_stop_on_keeps_going_past_a_terminal_status():
    """`stop_on=()` is the `run_tree` case: a SUCCESS is not a reason to stop."""
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Success(name="done")),
        rate=None,
        max_ticks=5,
        stop_on=(),
        signals=(),
    )
    assert runner.run() == EXIT_OK
    assert runner.ticks == 5


def test_stop_on_ignores_a_status_it_was_not_given():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Failure(name="nope")),
        rate=None,
        max_ticks=3,
        stop_on=(STATUS.SUCCESS,),
        signals=(),
    )
    assert runner.run() == EXIT_OK
    assert runner.ticks == 3


def test_on_tick_runs_after_every_tick():
    seen = []
    tree = tree_of(py_trees.behaviours.Running(name="forever"))
    runner = TreeRunner(
        tree, rate=None, max_ticks=3, signals=(), on_tick=lambda t: seen.append(t.count)
    )
    runner.run()
    assert seen == [1, 2, 3]


# -- rate and pacing ----------------------------------------------------------


@pytest.mark.parametrize(
    ("rate", "period"),
    [(20.0, 0.05), (0.5, 2.0), (1.0, 1.0), (100.0, 0.01)],
)
def test_rate_is_the_reciprocal_of_the_period(rate, period):
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")), rate=rate, signals=()
    )
    assert runner.rate == rate
    assert runner.period == pytest.approx(period)


def test_rate_none_reports_no_period():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")), rate=None, signals=()
    )
    assert runner.rate is None
    assert runner.period == 0.0


@pytest.mark.parametrize("rate", [0.0, -1.0, -0.001, float("nan"), float("inf")])
def test_invalid_rate_raises(rate):
    with pytest.raises(ValueError, match="rate"):
        TreeRunner(tree_of(py_trees.behaviours.Running(name="forever")), rate=rate)


def test_negative_max_ticks_raises():
    with pytest.raises(ValueError, match="max_ticks"):
        TreeRunner(tree_of(py_trees.behaviours.Running(name="forever")), max_ticks=-1)


def test_non_positive_setup_timeout_raises():
    with pytest.raises(ValueError, match="setup_timeout"):
        TreeRunner(
            tree_of(py_trees.behaviours.Running(name="forever")), setup_timeout=0.0
        )


def test_period_pacing_sleeps_the_remainder_of_the_period():
    clock = RecordingClock()
    tree = tree_of(SlowBehaviour("slow", clock, duration=0.02))
    runner = TreeRunner(tree, rate=20.0, max_ticks=3, signals=(), clock=clock)
    runner.run()
    # period 0.05 - tick 0.02 = 0.03, three times over.
    assert runner.overruns == 0
    assert runner.ticks == 3
    assert clock.sleeps == pytest.approx([0.03, 0.03, 0.03])


def test_pacing_sleeps_zero_when_the_tick_overruns():
    clock = RecordingClock()
    tree = tree_of(SlowBehaviour("slow", clock, duration=0.08))
    runner = TreeRunner(tree, rate=20.0, max_ticks=2, signals=(), clock=clock)
    runner.run()
    assert clock.sleeps == [0.0, 0.0]


def test_overrun_counted_not_compensated():
    """A 3x-period tick must not buy the next ticks a catch-up burst."""
    clock = RecordingClock()
    tree = tree_of(SlowBehaviour("slow", clock, duration=0.15))
    runner = TreeRunner(tree, rate=20.0, max_ticks=3, signals=(), clock=clock)
    runner.run()
    assert runner.overruns == 3
    assert runner.ticks == 3
    # Every sleep is zero: the loop runs as fast as it can and never fires
    # extra ticks to make up the shortfall.
    assert clock.sleeps == [0.0, 0.0, 0.0]


def test_unpaced_runner_never_sleeps_and_counts_no_overruns():
    clock = RecordingClock()
    tree = tree_of(SlowBehaviour("slow", clock, duration=10.0))
    runner = TreeRunner(tree, rate=None, max_ticks=3, signals=(), clock=clock)
    runner.run()
    assert clock.sleeps == []
    assert runner.overruns == 0
    assert runner.ticks == 3


# -- stop ---------------------------------------------------------------------


def test_stop_from_another_thread_exits_at_a_tick_boundary():
    log = []
    runner = TreeRunner(tree_of(SpanBehaviour("span", log)), rate=None, signals=())
    thread = run_in_thread(runner)
    time.sleep(0.05)
    runner.stop()
    thread.join(timeout=2.0)

    assert not thread.is_alive()
    assert runner.ticks > 0
    # Never cut off mid-tick: every enter has its matching leave.
    assert log.count("enter") == log.count("leave")
    assert log[-1] == "leave"


def test_stop_carries_its_exit_code():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")), rate=None, signals=()
    )
    thread = run_in_thread(runner)
    time.sleep(0.02)
    runner.stop(42)
    thread.join(timeout=2.0)
    assert runner.exit_code == 42


# -- pause / resume / step ----------------------------------------------------


def test_pause_blocks_ticking():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")), rate=None, signals=()
    )
    runner.pause()
    thread = run_in_thread(runner)
    time.sleep(0.2)

    assert runner.ticks == 0
    assert runner.state is RunnerState.PAUSED

    runner.stop()
    thread.join(timeout=2.0)
    assert not thread.is_alive()


def test_pause_twice_is_a_no_op():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")), rate=None, signals=()
    )
    runner.pause()
    runner.pause()
    thread = run_in_thread(runner)
    time.sleep(0.15)
    assert runner.ticks == 0
    runner.resume()
    time.sleep(0.05)
    runner.stop()
    thread.join(timeout=2.0)
    assert runner.ticks > 0


def test_resume_releases_the_hold():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")), rate=None, signals=()
    )
    runner.pause()
    thread = run_in_thread(runner)
    time.sleep(0.15)
    assert runner.ticks == 0

    runner.resume()
    time.sleep(0.15)
    ticked = runner.ticks
    runner.stop()
    thread.join(timeout=2.0)
    assert ticked > 0


def test_step_while_paused_ticks_exactly_n_times():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")), rate=None, signals=()
    )
    runner.pause()
    thread = run_in_thread(runner)
    time.sleep(0.1)
    assert runner.ticks == 0

    runner.step(2)
    time.sleep(0.2)
    assert runner.ticks == 2

    # And it goes straight back to holding.
    time.sleep(0.2)
    assert runner.ticks == 2
    assert runner.state is RunnerState.PAUSED

    runner.stop()
    thread.join(timeout=2.0)


def test_step_from_running_is_allowed():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")), rate=None, signals=()
    )
    thread = run_in_thread(runner)
    runner.step(1)
    time.sleep(0.05)
    runner.stop()
    thread.join(timeout=2.0)
    assert runner.ticks > 0


@pytest.mark.parametrize("n", [0, -1])
def test_step_rejects_a_non_positive_count(n):
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")), rate=None, signals=()
    )
    with pytest.raises(ValueError, match="n"):
        runner.step(n)


def test_stop_while_paused_exits_promptly():
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")), rate=None, signals=()
    )
    runner.pause()
    thread = run_in_thread(runner)
    time.sleep(0.1)

    runner.stop()
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    assert runner.state is RunnerState.STOPPED


# -- teardown -----------------------------------------------------------------


def test_teardown_order_is_terminate_then_shutdown_then_close():
    log = []
    tree = tree_of(RecordingBehaviour("worker", log))
    tree.visitors.append(RecordingVisitor(log))
    TreeRunner(tree, rate=None, max_ticks=1, signals=()).run()
    assert log == ["terminate", "shutdown", "close"]


def test_teardown_runs_on_exception_and_the_exception_propagates():
    log = []
    tree = tree_of(RaiseBehavior(name="boom", exception=ValueError("kaboom")))
    tree.visitors.append(RecordingVisitor(log))
    runner = TreeRunner(tree, rate=None, max_ticks=3, signals=())

    with pytest.raises(ValueError, match="kaboom"):
        runner.run()

    assert log == ["close"]
    assert runner.exit_code == EXIT_SOFTWARE
    assert runner.state is RunnerState.STOPPED


def test_one_closeable_failure_does_not_block_the_others():
    log = []
    tree = tree_of(py_trees.behaviours.Running(name="forever"))
    tree.visitors.append(RecordingVisitor(log, label="first", raises=True))
    tree.visitors.append(RecordingVisitor(log, label="second"))
    tree.visitors.append(RecordingVisitor(log, label="third"))

    assert TreeRunner(tree, rate=None, max_ticks=1, signals=()).run() == EXIT_OK
    assert log == ["first", "second", "third"]


def test_a_visitor_without_close_is_left_alone():
    tree = tree_of(py_trees.behaviours.Running(name="forever"))
    plain = py_trees.visitors.VisitorBase()
    tree.visitors.append(plain)
    assert not isinstance(plain, Closeable)
    assert TreeRunner(tree, rate=None, max_ticks=1, signals=()).run() == EXIT_OK


# -- setup --------------------------------------------------------------------


class CountingSetupBehaviour(py_trees.behaviour.Behaviour):
    def __init__(self, name):
        super().__init__(name=name)
        self.setups = 0

    def setup(self, **kwargs):
        self.setups += 1

    def update(self):
        return STATUS.SUCCESS


class FailingSetupBehaviour(py_trees.behaviour.Behaviour):
    def setup(self, **kwargs):
        raise RuntimeError("no such window")

    def update(self):
        return STATUS.SUCCESS


def test_setup_error_names_the_last_completed_node():
    root = py_trees.composites.Sequence(
        name="root",
        memory=True,
        children=[
            CountingSetupBehaviour("open_furnace_checksum"),
            FailingSetupBehaviour(name="attach_window"),
        ],
    )
    runner = TreeRunner(tree_of(root), rate=None, signals=())

    with pytest.raises(SetupError, match="open_furnace_checksum") as caught:
        runner.setup()

    assert caught.value.last_node is not None
    assert caught.value.last_node.name == "open_furnace_checksum"
    assert isinstance(caught.value.__cause__, RuntimeError)


def test_run_reports_a_setup_failure_as_exit_code_two():
    root = py_trees.composites.Sequence(
        name="root", memory=True, children=[FailingSetupBehaviour(name="attach")]
    )
    runner = TreeRunner(tree_of(root), rate=None, max_ticks=1, signals=())
    assert runner.run() == EXIT_SETUP_FAILED
    assert runner.ticks == 0


def test_setup_is_not_repeated_if_already_run():
    node = CountingSetupBehaviour("once")
    runner = TreeRunner(tree_of(node), rate=None, max_ticks=1, signals=())
    runner.setup()
    runner.setup()
    runner.run()
    assert node.setups == 1


# -- signals ------------------------------------------------------------------


def test_signal_handlers_are_restored_after_run():
    before = signal.getsignal(signal.SIGUSR1)
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")),
        rate=None,
        max_ticks=1,
        signals=(signal.SIGUSR1,),
    )
    runner.run()
    assert signal.getsignal(signal.SIGUSR1) is before


def test_signal_handlers_are_restored_after_an_exception():
    before = signal.getsignal(signal.SIGUSR1)
    tree = tree_of(RaiseBehavior(name="boom", exception=ValueError))
    runner = TreeRunner(tree, rate=None, signals=(signal.SIGUSR1,))
    with pytest.raises(ValueError):
        runner.run()
    assert signal.getsignal(signal.SIGUSR1) is before


def test_non_main_thread_skips_signal_handlers():
    before = signal.getsignal(signal.SIGUSR1)
    runner = TreeRunner(
        tree_of(py_trees.behaviours.Running(name="forever")),
        rate=None,
        max_ticks=2,
        signals=(signal.SIGUSR1,),
    )
    thread = run_in_thread(runner)
    thread.join(timeout=2.0)

    assert not thread.is_alive()
    assert runner.ticks == 2
    assert signal.getsignal(signal.SIGUSR1) is before


# -- restart ------------------------------------------------------------------


def test_restart_resets_the_subtree_and_the_counters():
    log = []
    tree = tree_of(RecordingBehaviour("worker", log))
    runner = TreeRunner(tree, rate=None, max_ticks=2, signals=())
    runner.run()
    assert runner.ticks == 2

    log.clear()
    runner.restart()
    assert runner.ticks == 0
    assert runner.overruns == 0
    assert runner.exit_code == EXIT_OK
    assert runner.state is RunnerState.IDLE

    assert runner.run() == EXIT_OK
    assert runner.ticks == 2


# -- teardown keeps going -----------------------------------------------------


def test_teardown_continues_when_root_stop_raises():
    log = []

    class BadTerminate(RecordingBehaviour):
        def terminate(self, new_status):
            raise RuntimeError("terminate blew up")

    tree = tree_of(BadTerminate("worker", log))
    tree.visitors.append(RecordingVisitor(log))

    assert TreeRunner(tree, rate=None, max_ticks=1, signals=()).run() == EXIT_OK
    # shutdown() and the visitor still ran despite the failed terminate().
    assert log == ["shutdown", "close"]


def test_teardown_continues_when_tree_shutdown_raises():
    log = []

    class BadShutdown(RecordingBehaviour):
        def shutdown(self):
            raise RuntimeError("shutdown blew up")

    tree = tree_of(BadShutdown("worker", log))
    tree.visitors.append(RecordingVisitor(log))

    assert TreeRunner(tree, rate=None, max_ticks=1, signals=()).run() == EXIT_OK
    assert log == ["terminate", "close"]
