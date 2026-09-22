#!/usr/bin/env python
import logging
import re

import py_trees

from py_branches.visitors import StatusTransitionVisitor


_ANSI_RE = re.compile(r'\033\[[0-9;]*m')
_VISITOR_LOGGER = 'py_branches.visitors'


def _plain(message):
    return _ANSI_RE.sub('', message)


def _messages(caplog, logger_name=_VISITOR_LOGGER):
    return [_plain(r.message) for r in caplog.records if r.name == logger_name]


def test_status_transition_visitor_logs_on_transition(caplog):
    caplog.set_level(logging.INFO, logger=_VISITOR_LOGGER)
    success = py_trees.behaviours.Success('s')
    visitor = StatusTransitionVisitor()

    success.tick_once()
    visitor.run(success)

    assert _messages(caplog) == ['[s] SUCCESS']


def test_status_transition_visitor_is_quiet_while_status_is_unchanged(caplog):
    caplog.set_level(logging.INFO, logger=_VISITOR_LOGGER)
    success = py_trees.behaviours.Success('s')
    visitor = StatusTransitionVisitor()

    for _ in range(3):
        success.tick_once()
        visitor.run(success)

    # Three ticks, one transition into SUCCESS -> a single line.
    assert _messages(caplog) == ['[s] SUCCESS']


def test_status_transition_visitor_logs_each_distinct_transition(caplog):
    caplog.set_level(logging.INFO, logger=_VISITOR_LOGGER)
    # Ticks RUNNING twice, then SUCCESS.
    counter = py_trees.behaviours.TickCounter('tc', 2, py_trees.common.Status.SUCCESS)
    visitor = StatusTransitionVisitor()

    while counter.status != py_trees.common.Status.SUCCESS:
        counter.tick_once()
        visitor.run(counter)

    assert _messages(caplog) == ['[tc] RUNNING', '[tc] SUCCESS']


def test_status_transition_visitor_skips_behaviours_with_children(caplog):
    caplog.set_level(logging.INFO, logger=_VISITOR_LOGGER)
    child = py_trees.behaviours.Success('child')
    selector = py_trees.composites.Selector('selector', False, [child])
    visitor = StatusTransitionVisitor()

    selector.tick_once()
    visitor.run(selector)

    # Composites are skipped; only leaves are reported.
    assert _messages(caplog) == []


def test_status_transition_visitor_does_not_log_invalid(caplog):
    caplog.set_level(logging.INFO, logger=_VISITOR_LOGGER)
    success = py_trees.behaviours.Success('s')
    visitor = StatusTransitionVisitor()

    # A behaviour is INVALID before its first tick.
    assert success.status == py_trees.common.Status.INVALID
    visitor.run(success)

    assert _messages(caplog) == []


def test_status_transition_visitor_records_invalid_as_seen(caplog):
    caplog.set_level(logging.INFO, logger=_VISITOR_LOGGER)
    success = py_trees.behaviours.Success('s')
    visitor = StatusTransitionVisitor()

    # INVALID is stored as last-seen even though it is not logged, so the
    # later transition to SUCCESS is still reported exactly once.
    visitor.run(success)
    success.tick_once()
    visitor.run(success)
    visitor.run(success)

    assert _messages(caplog) == ['[s] SUCCESS']


def test_status_transition_visitor_tracks_duplicate_names_separately(caplog):
    caplog.set_level(logging.INFO, logger=_VISITOR_LOGGER)
    first = py_trees.behaviours.Success('dup')
    second = py_trees.behaviours.Success('dup')
    visitor = StatusTransitionVisitor()

    first.tick_once()
    second.tick_once()
    visitor.run(first)
    visitor.run(second)

    # Keyed by id, not name, so both are reported.
    assert _messages(caplog) == ['[dup] SUCCESS', '[dup] SUCCESS']


def test_status_transition_visitor_colors_by_status(caplog):
    caplog.set_level(logging.INFO, logger=_VISITOR_LOGGER)
    counter = py_trees.behaviours.TickCounter('tc', 1, py_trees.common.Status.SUCCESS)
    visitor = StatusTransitionVisitor()

    while counter.status != py_trees.common.Status.SUCCESS:
        counter.tick_once()
        visitor.run(counter)

    raw = [r.message for r in caplog.records if r.name == _VISITOR_LOGGER]
    assert raw[0].startswith('\033[37m')   # RUNNING -> white
    assert raw[-1].startswith('\033[32m')  # SUCCESS -> green
    assert all(m.endswith('\033[0m') for m in raw)


def test_status_transition_visitor_honours_injected_logger_and_level(caplog):
    caplog.set_level(logging.DEBUG, logger='custom.visitor.logger')
    logger = logging.getLogger('custom.visitor.logger')
    success = py_trees.behaviours.Success('s')
    visitor = StatusTransitionVisitor(logger=logger, level=logging.DEBUG)

    success.tick_once()
    visitor.run(success)

    records = [r for r in caplog.records if r.name == 'custom.visitor.logger']
    assert [_plain(r.message) for r in records] == ['[s] SUCCESS']
    assert records[0].levelno == logging.DEBUG
    # Nothing leaked onto the module logger.
    assert _messages(caplog) == []


def test_status_transition_visitor_integrates_with_behaviour_tree(caplog):
    caplog.set_level(logging.INFO, logger=_VISITOR_LOGGER)
    child = py_trees.behaviours.Success('leaf')
    selector = py_trees.composites.Selector('root', False, [child])
    tree = py_trees.trees.BehaviourTree(selector)
    visitor = StatusTransitionVisitor()
    tree.add_visitor(visitor)

    tree.tick()
    tree.tick()

    messages = _messages(caplog)
    # The root composite is skipped; only the leaf is reported. The exact
    # count is left open because the composite may invalidate its child
    # between ticks, which is a legitimate extra transition.
    assert messages
    assert all(m == '[leaf] SUCCESS' for m in messages)
