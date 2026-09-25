#!/usr/bin/env python3
"""Make a child's first SUCCESS permanent.

A single decorator, :class:`Latch`, for work that should happen once and then
report success forever after.
"""
import py_trees


class Latch(py_trees.decorators.Decorator):
    '''
    Once the child returns SUCCESS, latches to SUCCESS and stops re-running
    the child until :meth:`reset` is called.

    - While unlatched: child is ticked normally and its status is passed through.
    - On first SUCCESS from child: latch engages.
    - While latched: child is NOT ticked; this decorator returns SUCCESS.
    - On :meth:`reset`: latch disengages and the child will run again on the
      next tick.

    The latch state persists across tree re-entries (i.e. it is NOT cleared by
    ``initialise()``).  To get a fresh latch, call :meth:`reset` explicitly.

    A child that returns FAILURE does not latch; it will be retried on the
    next tick.

    Args:
        child (Behaviour): The child behavior to latch.
        name (str): Name of this decorator.

    Example:
        .. code-block:: python

            child = ExpensiveSetupBehavior(name="Setup")
            # Run setup once; once it succeeds, always return SUCCESS without
            # re-running it.
            latched = Latch(child, name="Latch")

            # Later, to trigger a re-run:
            latched.reset()
    '''
    def __init__(self, child: py_trees.behaviour.Behaviour,
                       name: str):
        super(Latch, self).__init__(name=name, child=child)
        self._latched = False

    def reset(self) -> None:
        '''Disengage the latch so the child will run again on the next tick.'''
        self._latched = False

    def tick(self):
        if self._latched:
            self.stop(py_trees.common.Status.SUCCESS)
            yield self
        else:
            for node in super().tick():
                yield node

    def update(self) -> py_trees.common.Status:
        if self.decorated.status == py_trees.common.Status.SUCCESS:
            self._latched = True
        return self.decorated.status
