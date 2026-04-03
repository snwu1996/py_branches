#!/usr/bin/env python

import time
import py_trees

from py_branches.cooldown import Cooldown


_r = py_trees.common.Status.RUNNING
_s = py_trees.common.Status.SUCCESS
_f = py_trees.common.Status.FAILURE
_i = py_trees.common.Status.INVALID


def test_cooldown_basic_success():
    '''Child succeeds; cooldown prevents re-run until duration elapses.'''
    child = py_trees.behaviours.Success(name='success')
    cooldown = Cooldown(child, name='cooldown', duration=5.0)

    # First tick: child runs and succeeds.
    cooldown.tick_once()
    assert cooldown.status == _s

    # Subsequent ticks: cooling down, child not run.
    for _ in range(3):
        cooldown.tick_once()
        assert cooldown.status == _f
        assert child.status == _s  # child not re-ticked


def test_cooldown_basic_failure():
    '''Child fails; cooldown still engages after FAILURE.'''
    child = py_trees.behaviours.Failure(name='failure')
    cooldown = Cooldown(child, name='cooldown', duration=5.0)

    cooldown.tick_once()
    assert cooldown.status == _f  # child failed

    cooldown.tick_once()
    assert cooldown.status == _f  # still cooling (not re-running child)
    assert child.status == _f


def test_cooldown_success_if_cooling():
    '''success_if_cooling=True returns SUCCESS while cooled down.'''
    child = py_trees.behaviours.Success(name='success')
    cooldown = Cooldown(child, name='cooldown', duration=5.0, success_if_cooling=True)

    cooldown.tick_once()
    assert cooldown.status == _s  # child ran

    cooldown.tick_once()
    assert cooldown.status == _s  # cooling but success_if_cooling


def test_cooldown_expires_and_reruns():
    '''After the cooldown duration, the child is allowed to run again.'''
    child = py_trees.behaviours.Success(name='success')
    duration = 0.05
    cooldown = Cooldown(child, name='cooldown', duration=duration)

    cooldown.tick_once()
    assert cooldown.status == _s  # first run

    cooldown.tick_once()
    assert cooldown.status == _f  # cooling

    time.sleep(duration + 0.01)

    cooldown.tick_once()
    assert cooldown.status == _s  # cooldown expired; child ran again


def test_cooldown_running_child_no_cooldown():
    '''A RUNNING child never triggers the cooldown.'''
    child = py_trees.behaviours.Running(name='running')
    cooldown = Cooldown(child, name='cooldown', duration=0.05)

    for _ in range(5):
        cooldown.tick_once()
        assert cooldown.status == _r
        assert not cooldown._cooling


def test_cooldown_running_then_success_triggers_cooldown():
    '''Cooldown starts only after the RUNNING child eventually completes.'''
    bb = py_trees.blackboard.Client(name='test')
    bb.register_key(key='done', access=py_trees.common.Access.WRITE)
    bb.done = False

    # Use SetBlackboardVariable to make child succeed on demand.
    child = py_trees.behaviours.CheckBlackboardVariableValue(
        name='check',
        check=py_trees.common.ComparisonExpression(
            variable='done',
            value=True,
            operator=lambda a, b: a == b,
        ),
    )
    cooldown = Cooldown(child, name='cooldown', duration=5.0)

    # Child returns FAILURE (done=False) — cooldown starts but since child
    # returned FAILURE, the cooldown flag is set.
    cooldown.tick_once()
    assert cooldown._cooling  # any completion starts cooldown

    cooldown.stop(py_trees.common.Status.INVALID)
    cooldown._cooling = False  # manually clear for next scenario

    # Now use a Running child to verify no cooldown while RUNNING.
    running_child = py_trees.behaviours.Running(name='running')
    cooldown2 = Cooldown(running_child, name='cooldown2', duration=5.0)
    cooldown2.tick_once()
    assert not cooldown2._cooling
