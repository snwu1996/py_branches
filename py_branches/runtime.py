#!/usr/bin/env python3
"""Running a tree as a process — pacing, signals, exit codes and teardown.

`py_trees <https://py-trees.readthedocs.io/>`_ already knows how to tick a tree
on a schedule: :meth:`py_trees.trees.BehaviourTree.tick_tock` paces, bounds the
iteration count, stops on a terminal status and runs pre/post handlers. What it
has no answer for is the *process* around the loop — what exit code to report,
what to do about ``SIGTERM``, and how to guarantee that every behavior gets torn
down on the way out. That is what this module is for.

============================== ================================================
Name                           What it is
============================== ================================================
:class:`TreeRunner`            The loop: rate, signals, exit code, teardown
:class:`RunnerState`           Where a runner is in its lifecycle
:class:`Closeable`             The protocol a visitor satisfies to be closed
:class:`SetupError`            Setup failed, naming the node it stalled after
:class:`ShutdownRequest`       A request to end the run, carrying an exit code
:class:`RequestShutdown`       Behavior that files one and lets the tick finish
:class:`ExitBehavior`          :class:`RequestShutdown` with a shorter name
:class:`RaiseBehavior`         Raise an exception from a tick, deliberately
:data:`SHUTDOWN_KEY`           The reserved blackboard key a request lands on
============================== ================================================

**Rate, not period.** :class:`TreeRunner` is configured in ticks per second,
because that is the number an operator thinks in; the period is its reciprocal
and is derived. ``rate=20.0`` is a 0.05 s period, ``rate=0.5`` is one tick every
two seconds, and ``rate=None`` means free-running with no pacing at all.

**Shutdown is requested, not thrown.** :class:`RequestShutdown` writes a
:class:`ShutdownRequest` to the blackboard and returns SUCCESS; the runner reads
it *after* the tick returns and leaves at the loop boundary. The tick therefore
completes normally — visitors finalise, ``tree.count`` increments, the final
state reaches any publisher attached to the tree. Calling :func:`sys.exit` from
inside ``update()`` loses all three, which is why nothing here does it.

Example:
    .. testcode::

        import py_trees
        from py_branches.runtime import TreeRunner

        tree = py_trees.trees.BehaviourTree(
            py_trees.behaviours.Success(name="Work")
        )
        runner = TreeRunner(tree, rate=20.0, max_ticks=1, signals=())
        assert runner.period == 0.05
        assert runner.run() == 0
"""

import contextlib
import dataclasses
import enum
import logging
import math
import signal
import threading
from collections.abc import Callable
from typing import Protocol
from typing import runtime_checkable

import py_trees

from .clock import Clock
from .clock import default_clock

logger = logging.getLogger(__name__)

#: Reserved blackboard key holding a pending :class:`ShutdownRequest`.
#:
#: Namespaced with a slash so it cannot collide with a tree's own variables,
#: and a plain blackboard key so that any visitor snapshotting the blackboard
#: shows a pending shutdown without needing to know this module exists.
SHUTDOWN_KEY = "py_branches/shutdown"

#: Everything went as asked.
EXIT_OK = 0
#: ``stop_on`` was reached with FAILURE.
EXIT_FAILURE = 1
#: :meth:`TreeRunner.setup` failed — a timeout, or a behavior that raised.
EXIT_SETUP_FAILED = 2
#: An exception escaped a tick. ``EX_SOFTWARE`` from ``sysexits.h``.
EXIT_SOFTWARE = 70

# How long a paused loop sleeps between checks. Short enough to stay responsive
# to a signal or a stop() from another thread, long enough not to busy-wait.
_PAUSE_SLICE = 0.05

# Minimum gap between overrun WARNINGs. A tree that overruns usually overruns
# every tick, and an unthrottled warning would bury everything else in the log.
_OVERRUN_LOG_INTERVAL = 5.0


class RunnerState(enum.Enum):
    """Where a :class:`TreeRunner` is in its lifecycle."""

    #: Constructed, or finished setting up, but not looping.
    IDLE = "idle"
    #: Inside :meth:`TreeRunner.setup`.
    SETUP = "setup"
    #: Ticking.
    RUNNING = "running"
    #: Holding, by :meth:`TreeRunner.pause`.
    PAUSED = "paused"
    #: Leaving the loop and tearing down.
    STOPPING = "stopping"
    #: Teardown complete.
    STOPPED = "stopped"


@runtime_checkable
class Closeable(Protocol):
    """Anything with a ``close()``, which a runner calls during teardown.

    A :class:`typing.Protocol`, so there is no base class to inherit: a visitor
    holding a socket, a file handle or a thread qualifies simply by having the
    method. That is the point — it means a runner never has to name a specific
    visitor class in an ``isinstance`` check to know that it needs closing.
    """

    def close(self) -> None:
        """Release whatever the object holds.

        Called once, during teardown, inside its own ``try``/``except`` — a
        failure here is logged and the remaining visitors are still closed.
        """
        ...


class SetupError(RuntimeError):
    """Raised when :meth:`TreeRunner.setup` fails.

    ``py_trees`` reports a setup timeout as a bare :exc:`RuntimeError`, which
    says that something hung without saying what. This carries the last node
    that finished setting up, so the message names the node setup stalled
    *after*.

    Args:
        message (str): The formatted message, naming the last completed node.

    Attributes:
        last_node (Optional[Behaviour]): The most recent behavior whose
            ``setup()`` completed, or None if none did.
    """

    def __init__(
        self,
        message: str,
        *,
        last_node: py_trees.behaviour.Behaviour | None = None,
    ) -> None:
        super().__init__(message)
        self.last_node = last_node


@dataclasses.dataclass(frozen=True)
class ShutdownRequest(Exception):
    """A request to end the run, carrying the exit code it should end with.

    Both a payload and an exception, deliberately. The cooperative path writes
    it to the blackboard; :class:`ExitBehavior` with ``immediate=True`` raises
    it. One type across both paths means the two cannot drift apart on what a
    shutdown carries.

    Args:
        code (int): Exit code the runner should return. Default 0.
        reason (str): Human-readable why, for the log line. Default ``''``.
        requested_by (str): Name of the behavior or signal that asked. Default
            ``''``.

    Example:
        .. testcode::

            from py_branches.runtime import ShutdownRequest

            request = ShutdownRequest(code=42, reason="out of ore")
            assert request.code == 42
    """

    code: int = 0
    reason: str = ""
    requested_by: str = ""

    def __str__(self) -> str:
        """Return a one-line description naming the requester and the code.

        Returns:
            str: Something like ``"shutdown requested by 'exit_bot' (code 0)"``.
        """
        who = self.requested_by or "<unknown>"
        why = f": {self.reason}" if self.reason else ""
        return f"shutdown requested by {who!r} (code {self.code}){why}"


class RequestShutdown(py_trees.behaviour.Behaviour):
    """File a shutdown request and let the tick finish normally.

    Writes a :class:`ShutdownRequest` to :data:`SHUTDOWN_KEY` and returns
    ``status``. It does **not** raise, so the rest of the tick runs: the tree's
    visitors reach their ``finalise()``, ``tree.count`` increments, and the
    final state reaches whatever is watching. A :class:`TreeRunner` reads the
    key once the tick returns and leaves at the loop boundary.

    **First write wins.** If a request is already pending, this logs at DEBUG
    and leaves the existing one alone, so the exit code does not depend on the
    order the tree happened to be traversed in.

    Ticked in a tree with no runner, it simply leaves the key set and nothing
    else happens. That is the intended degradation — the caller driving
    ``tree.tick()`` by hand can check the key itself.

    Args:
        name (str): Name of this behavior. Also recorded as the request's
            ``requested_by``.
        code (int): Exit code to request, keyword-only. Default 0.
        reason (str): Why, for the log line, keyword-only. Default ``''``.
        status (Status): What to report to the parent, keyword-only. Default
            SUCCESS, so it composes at the end of a Sequence; FAILURE is useful
            as a Selector's last resort.

    Example:
        .. testcode::

            from py_branches.runtime import RequestShutdown

            # Constructed, not ticked - ticking would set the reserved key.
            done = RequestShutdown(name="all_done", code=0, reason="finished")
    """

    def __init__(
        self,
        name: str,
        *,
        code: int = 0,
        reason: str = "",
        status: py_trees.common.Status = py_trees.common.Status.SUCCESS,
    ) -> None:
        super().__init__(name=name)
        self._request = ShutdownRequest(code=code, reason=reason, requested_by=name)
        self._status = status
        self._blackboard = self.attach_blackboard_client(name=name)
        self._blackboard.register_key(
            key=SHUTDOWN_KEY, access=py_trees.common.Access.WRITE
        )

    @property
    def request(self) -> ShutdownRequest:
        """The request this behavior files.

        Returns:
            ShutdownRequest: Fixed at construction; frozen, so it is safe to
            hand out.
        """
        return self._request

    def update(self) -> py_trees.common.Status:
        """Write the request if none is pending, then report ``status``.

        Returns:
            Status: The ``status`` given to the constructor, unconditionally —
            whether or not this behavior's request was the one that won.
        """
        pending = _pending_shutdown()
        if pending is None:
            self._blackboard.set(SHUTDOWN_KEY, self._request)
            self.logger.debug(f"{self.name}: filed {self._request}")
        else:
            self.logger.debug(
                f"{self.name}: a shutdown is already pending ({pending}); "
                f"ignoring code {self._request.code}"
            )
        return self._status


class ExitBehavior(RequestShutdown):
    """End the run. Cooperative by default, raising only if asked.

    A thin :class:`RequestShutdown` with a default name, kept as a separate
    class because "exit" is what a tree author reaches for.

    ``immediate=True`` raises the :class:`ShutdownRequest` from inside
    ``update()`` instead of filing it. A runner catches it at the loop boundary
    and still tears down, but the tick is abandoned where it stands — so that
    tick's visitors never reach ``finalise()`` and ``tree.count`` never
    increments. Use it only when the tree must stop mid-action; otherwise the
    default loses nothing.

    Args:
        name (str): Name of this behavior. Default ``'exit'``.
        code (int): Exit code to request, keyword-only. Default 0.
        reason (str): Why, for the log line, keyword-only. Default ``''``.
        immediate (bool): Raise instead of filing, keyword-only. Default False.
        status (Status): What to report to the parent when not immediate,
            keyword-only. Default SUCCESS.

    Example:
        .. testcode::

            from py_branches.runtime import ExitBehavior

            # Constructed, not ticked - ticking would set the reserved key.
            quit_cleanly = ExitBehavior(name="exit_bot", code=0)
    """

    def __init__(
        self,
        name: str = "exit",
        *,
        code: int = 0,
        reason: str = "",
        immediate: bool = False,
        status: py_trees.common.Status = py_trees.common.Status.SUCCESS,
    ) -> None:
        super().__init__(name=name, code=code, reason=reason, status=status)
        self._immediate = immediate

    def update(self) -> py_trees.common.Status:
        """File the request, or raise it when ``immediate``.

        Returns:
            Status: As :meth:`RequestShutdown.update`, when not immediate.

        Raises:
            ShutdownRequest: When constructed with ``immediate=True``.
        """
        if self._immediate:
            self.logger.info(f"{self.name}: {self._request} (immediate)")
            raise self._request
        return super().update()


class RaiseBehavior(py_trees.behaviour.Behaviour):
    """Raise an exception from a tick, on purpose.

    For the branch of a tree that is only reachable when an assumption has
    already been violated. A runner runs its full teardown and then re-raises,
    so the traceback survives — a supervision layer that swallowed it would be
    worse than no supervision layer.

    Args:
        name (str): Name of this behavior.
        exception (Union[BaseException, Callable[[], BaseException]]): The
            exception to raise, or a zero-argument callable returning one. An
            exception *class* counts as a callable, so both
            ``RaiseBehavior('x', RuntimeError)`` and
            ``RaiseBehavior('x', RuntimeError('why'))`` work; a callable is
            evaluated on every tick, so each raise gets a fresh instance.

    Example:
        .. testcode::

            from py_branches.runtime import RaiseBehavior

            unreachable = RaiseBehavior(
                name="impossible",
                exception=lambda: AssertionError("bank was open and closed"),
            )
    """

    def __init__(
        self,
        name: str,
        exception: BaseException | Callable[[], BaseException],
    ) -> None:
        super().__init__(name=name)
        self._exception = exception

    def update(self) -> py_trees.common.Status:
        """Raise. Never returns.

        Returns:
            Status: Nothing is ever returned; the annotation is for the
            ``py_trees`` interface.

        Raises:
            BaseException: Whatever was handed to the constructor.
        """
        error = self._exception() if callable(self._exception) else self._exception
        raise error


def _pending_shutdown() -> ShutdownRequest | None:
    """Read the pending request off the blackboard, if there is one.

    Uses the class-level blackboard accessors rather than a client, so a reader
    needs no registration and no key access of its own.

    Returns:
        Optional[ShutdownRequest]: The pending request, or None if the key is
        unset or holds something that is not a request.
    """
    if not py_trees.blackboard.Blackboard.exists(SHUTDOWN_KEY):
        return None
    value = py_trees.blackboard.Blackboard.get(SHUTDOWN_KEY)
    if not isinstance(value, ShutdownRequest):
        logger.warning(
            f"{SHUTDOWN_KEY!r} holds {type(value).__name__}, not a ShutdownRequest; "
            f"ignoring it"
        )
        return None
    return value


def clear_shutdown_request() -> None:
    """Remove any pending request from the blackboard.

    Called by :meth:`TreeRunner.restart`. Useful directly when driving a tree
    by hand across several runs in one process — the key is global to the
    blackboard, so a request left over from a previous tree would otherwise
    stop the next one on its first tick.
    """
    py_trees.blackboard.Blackboard.unset(SHUTDOWN_KEY)


class _SetupProgressVisitor(py_trees.visitors.VisitorBase):
    """Records the last node to finish setting up.

    ``tree.setup()`` runs this after each node's ``setup()``, which makes it
    the built-in answer to "which behavior hung". Logs each node at DEBUG so a
    slow setup is visible while it happens, not only once it fails.
    """

    def __init__(self) -> None:
        super().__init__(full=False)
        self.last: py_trees.behaviour.Behaviour | None = None

    def run(self, behaviour: py_trees.behaviour.Behaviour) -> None:
        """Record ``behaviour`` as the most recently set-up node.

        Args:
            behaviour (Behaviour): The node whose ``setup()`` just returned.
        """
        self.last = behaviour
        logger.debug(f"setup complete: {behaviour.name}")


class TreeRunner:
    """Run a behavior tree as a process: paced, signal-aware, torn down.

    Wraps a :class:`py_trees.trees.BehaviourTree` in the lifecycle a long-lived
    bot needs. The pacing expression is taken verbatim from
    :meth:`py_trees.trees.BehaviourTree.tick_tock` — that part of ``py_trees``
    is already correct, and diverging from it would be a silent behavior
    change. Everything else is the part ``tick_tock`` has no opinion about:

    * an **exit code** that means something to ``systemd`` or a supervisor
    * **signal handling**, including a second signal that forces the issue
    * **teardown** that runs on every exit path, in a defined order
    * **setup diagnostics** that name the node setup stalled after
    * **pause / resume / step**, for reading a live tree instead of watching it
      blur past

    If all that is needed is a paced loop, use ``tick_tock``; this class is for
    a process that has to exit cleanly and report why.

    ``stop_on=()`` runs until told otherwise; ``stop_on=(SUCCESS, FAILURE)``
    runs a tree once and reports which way it went. One class covers both.

    Args:
        tree (BehaviourTree): The tree to run.
        rate (Optional[float]): Ticks per second, keyword-only. Default 20.0,
            which is a 0.05 s period. The period is the reciprocal of the rate.
            Pass None to free-run: no sleeping, and no overrun accounting,
            because there is no budget left to overrun.
        max_ticks (Optional[int]): Stop after this many ticks, keyword-only.
            Default None, meaning no limit.
        stop_on (Tuple[Status, ...]): Stop once the root reports one of these
            after a tick, keyword-only. Default ``()`` — never stop on status.
        signals (Tuple[Signals, ...]): Signals to handle, keyword-only. Default
            ``(SIGINT, SIGTERM)``. Pass ``()`` to install nothing, which is
            what a test or a runner on a worker thread wants.
        setup_timeout (float): Seconds :meth:`setup` waits, keyword-only.
            Default 15.0. Must be positive.
        on_tick (Optional[Callable[[BehaviourTree], None]]): Called after every
            tick, keyword-only. For a caller that wants a hook without
            attaching a visitor; an exception from it escapes like any other.
        clock (Optional[Clock]): Time source for pacing, keyword-only. Defaults
            to the real clock; pass a :class:`py_branches.clock.ManualClock` to
            make a pacing test exact.

    Raises:
        ValueError: If ``rate`` is not positive and finite, ``max_ticks`` is
            negative, or ``setup_timeout`` is not positive.

    Example:
        .. testcode::

            import py_trees
            from py_branches.runtime import TreeRunner

            tree = py_trees.trees.BehaviourTree(
                py_trees.behaviours.Success(name="Work")
            )
            # max_ticks and signals=() keep the example bounded and handlerless.
            runner = TreeRunner(
                tree,
                rate=20.0,
                max_ticks=1,
                stop_on=(py_trees.common.Status.SUCCESS,),
                signals=(),
            )
            assert runner.run() == 0
            assert runner.ticks == 1
    """

    def __init__(
        self,
        tree: py_trees.trees.BehaviourTree,
        *,
        rate: float | None = 20.0,
        max_ticks: int | None = None,
        stop_on: tuple[py_trees.common.Status, ...] = (),
        signals: tuple[signal.Signals, ...] = (signal.SIGINT, signal.SIGTERM),
        setup_timeout: float = 15.0,
        on_tick: Callable[[py_trees.trees.BehaviourTree], None] | None = None,
        clock: Clock | None = None,
    ) -> None:
        if rate is not None and (not math.isfinite(rate) or rate <= 0.0):
            raise ValueError(
                f"rate({rate}) must be a positive, finite number of ticks per "
                f"second, or None to run unpaced."
            )
        if max_ticks is not None and max_ticks < 0:
            raise ValueError(f"max_ticks({max_ticks}) must not be negative.")
        if setup_timeout <= 0.0:
            raise ValueError(f"setup_timeout({setup_timeout}) must be positive.")

        self._tree = tree
        self._rate = rate
        # The pacing expression works in seconds; 0.0 reads as "do not pace".
        self._period = 0.0 if rate is None else 1.0 / rate
        self._max_ticks = max_ticks
        self._stop_on = tuple(stop_on)
        self._signals = tuple(signals)
        self._setup_timeout = setup_timeout
        self._on_tick = on_tick
        self._clock = clock if clock is not None else default_clock()

        self._state = RunnerState.IDLE
        self._setup_done = False
        self._ticks = 0
        self._overruns = 0
        self._exit_code = EXIT_OK
        self._exit_code_set = False
        self._last_overrun_log: float | None = None

        self._stop_requested = threading.Event()
        self._pause_requested = threading.Event()
        self._steps_lock = threading.Lock()
        self._steps_remaining = 0

        self._saved_handlers: dict[signal.Signals, object] = {}
        self._signal_seen = False

    # -- Introspection --------------------------------------------------------

    @property
    def state(self) -> RunnerState:
        """Current lifecycle state.

        Returns:
            RunnerState: Where the runner is right now.
        """
        return self._state

    @property
    def ticks(self) -> int:
        """Number of ticks completed since construction or :meth:`restart`.

        Returns:
            int: Completed ticks.
        """
        return self._ticks

    @property
    def overruns(self) -> int:
        """Number of ticks that took longer than the period.

        Always zero when running unpaced (``rate=None``), because there is no
        period to exceed.

        Returns:
            int: Overrunning ticks since construction or :meth:`restart`.
        """
        return self._overruns

    @property
    def rate(self) -> float | None:
        """Configured rate in ticks per second, or None when unpaced.

        Returns:
            Optional[float]: The ``rate`` given to the constructor.
        """
        return self._rate

    @property
    def period(self) -> float:
        """Seconds per tick — the reciprocal of :attr:`rate`.

        Returns:
            float: ``1 / rate``, or 0.0 when running unpaced.
        """
        return self._period

    @property
    def exit_code(self) -> int:
        """The code the last :meth:`run` returned, or would return.

        Returns:
            int: See the module documentation for what each code means.
        """
        return self._exit_code

    # -- Lifecycle ------------------------------------------------------------

    def setup(self) -> None:
        """Set the tree up, naming the node it stalls after if it fails.

        Calls :meth:`py_trees.trees.BehaviourTree.setup` with a progress
        visitor. Calling it twice is a no-op — :meth:`run` calls it only if it
        has not already run, so an explicit ``setup()`` before ``run()`` costs
        nothing.

        ``py_trees`` implements the setup timeout with ``SIGUSR1`` and a
        :class:`threading.Timer`, which only works on the main thread. Off it,
        this falls back to waiting indefinitely and says so at DEBUG, rather
        than failing to set up at all over a timeout it cannot arm.

        Raises:
            SetupError: If setup times out or a behavior raises during it. The
                original exception is chained, and the message names the last
                node whose ``setup()`` completed.
        """
        if self._setup_done:
            return
        self._state = RunnerState.SETUP
        progress = _SetupProgressVisitor()
        timeout: float | py_trees.common.Duration = self._setup_timeout
        if threading.current_thread() is not threading.main_thread():
            logger.debug(
                "not on the main thread; setting up without the %ss timeout",
                self._setup_timeout,
            )
            timeout = py_trees.common.Duration.INFINITE
        try:
            self._tree.setup(timeout=timeout, visitor=progress)
        except Exception as error:
            self._exit_code = EXIT_SETUP_FAILED
            self._exit_code_set = True
            self._state = RunnerState.STOPPED
            last = progress.last.name if progress.last is not None else "<none>"
            raise SetupError(
                f"setup failed; last completed node was {last!r} "
                f"(timeout {self._setup_timeout}s)",
                last_node=progress.last,
            ) from error
        self._setup_done = True
        self._state = RunnerState.IDLE

    def run(self) -> int:
        """Tick until something says to stop, then tear down and report.

        Calls :meth:`setup` if it has not run, installs the configured signal
        handlers, and loops. Teardown runs on every exit path, including an
        exception.

        A setup failure is reported as exit code 2 rather than propagating,
        because it is an operational outcome with a diagnostic message
        attached. An exception out of a *tick* is a bug: teardown runs, the
        exit code is set to 70, and the exception is re-raised with its
        traceback intact.

        Returns:
            int: The exit code. 0 on a clean stop, 1 for a FAILURE in
            ``stop_on``, 2 for a setup failure, 70 for an escaped exception,
            130 for SIGINT, 143 for SIGTERM, or whatever code a
            :class:`ShutdownRequest` carried.

        Raises:
            BaseException: Anything a behavior raises during a tick, after
                teardown has completed. :class:`ShutdownRequest` and
                :exc:`KeyboardInterrupt` are the exceptions to that, and become
                exit codes instead.
        """
        if not self._setup_done:
            try:
                self.setup()
            except SetupError:
                logger.exception("setup failed; not starting the loop")
                self._teardown()
                return EXIT_SETUP_FAILED

        self._stop_requested.clear()
        self._signal_seen = False
        self._exit_code = EXIT_OK
        self._exit_code_set = False
        self._install_signal_handlers()
        self._state = RunnerState.RUNNING
        try:
            self._loop()
            self._resolve_exit_code()
        except ShutdownRequest as request:
            # ExitBehavior(immediate=True). The tick it came from was abandoned
            # part way, so that tick's visitors never finalised - which is the
            # documented cost of asking for an immediate exit.
            logger.info(f"{request} (immediate; that tick did not finalise)")
            self._exit_code = request.code
            self._exit_code_set = True
        except KeyboardInterrupt:
            # Only reachable when SIGINT was not among `signals`; with a handler
            # installed the interrupt arrives as a cooperative stop instead.
            logger.info("interrupted; shutting down")
            self._exit_code = 128 + int(signal.SIGINT)
            self._exit_code_set = True
        except BaseException:
            self._exit_code = EXIT_SOFTWARE
            self._exit_code_set = True
            raise
        finally:
            self._teardown()
        return self._exit_code

    def _loop(self) -> None:
        """Tick until :meth:`_should_continue` says otherwise."""
        while self._should_continue():
            if self._holding():
                self._state = RunnerState.PAUSED
                self._clock.sleep(self._pause_slice())
                continue

            self._state = RunnerState.RUNNING
            start = self._clock.time()
            self._tree.tick()
            self._ticks += 1
            self._consume_step()
            if self._on_tick is not None:
                self._on_tick(self._tree)
            if self._consume_shutdown_request():
                return

            if not self._period:
                continue
            elapsed = self._clock.time() - start
            if elapsed > self._period:
                # Counted and logged, never compensated. Firing a burst of
                # catch-up ticks in an RPA tree means a burst of clicks.
                self._overruns += 1
                self._log_overrun(elapsed)
            # Copied verbatim from py_trees.trees.BehaviourTree.tick_tock(): the
            # sleep is measured from the tick's start, so the period does not
            # drift by the tick's own duration.
            self._clock.sleep(max(0.0, self._period + start - self._clock.time()))

    def _should_continue(self) -> bool:
        """Decide whether to run another iteration.

        Returns:
            bool: False once a stop has been requested, ``max_ticks`` is
            exhausted, or the root has settled on a status in ``stop_on``.
        """
        if self._stop_requested.is_set():
            return False
        if self._max_ticks is not None and self._ticks >= self._max_ticks:
            return False
        if (
            self._stop_on
            and self._ticks > 0
            and self._tree.root.status in self._stop_on
        ):
            return False
        return True

    def _resolve_exit_code(self) -> None:
        """Derive the exit code from how the loop ended, if nothing set one."""
        if self._exit_code_set:
            return
        status = self._tree.root.status
        if self._stop_on and status in self._stop_on:
            self._exit_code = (
                EXIT_FAILURE if status == py_trees.common.Status.FAILURE else EXIT_OK
            )
        else:
            self._exit_code = EXIT_OK
        self._exit_code_set = True

    def _consume_shutdown_request(self) -> bool:
        """Act on a request filed during the tick that just finished.

        Returns:
            bool: True if a request was found and the loop should end.
        """
        request = _pending_shutdown()
        if request is None:
            return False
        logger.info(str(request))
        self._exit_code = request.code
        self._exit_code_set = True
        self._state = RunnerState.STOPPING
        return True

    def _log_overrun(self, elapsed: float) -> None:
        """Warn about an overrunning tick, at most once every few seconds.

        Args:
            elapsed (float): How long the tick actually took, in seconds.
        """
        now = self._clock.time()
        if (
            self._last_overrun_log is not None
            and now - self._last_overrun_log < _OVERRUN_LOG_INTERVAL
        ):
            return
        self._last_overrun_log = now
        logger.warning(
            f"tick {self._ticks} took {elapsed:.3f}s, over the {self._period:.3f}s "
            f"period ({self._overruns} overruns so far); not compensating"
        )

    # -- Control --------------------------------------------------------------

    def stop(self, code: int = EXIT_OK) -> None:
        """Ask the loop to finish, from a signal handler or another thread.

        Sets a flag read at the top of the loop, so the tick in flight always
        completes. Prompt from a paused runner too — the hold sleeps in short
        slices rather than blocking.

        Args:
            code (int): Exit code :meth:`run` should return. Default 0.
        """
        self._exit_code = code
        self._exit_code_set = True
        self._state = RunnerState.STOPPING
        self._stop_requested.set()

    def pause(self) -> None:
        """Hold at the next loop boundary. A no-op if already paused.

        For reading a live tree in a viewer, which is unworkable while it
        free-runs. The tick in flight completes first.
        """
        self._pause_requested.set()

    def resume(self) -> None:
        """Release a hold. A no-op if not paused."""
        self._pause_requested.clear()

    def step(self, n: int = 1) -> None:
        """Tick ``n`` more times, then go back to holding.

        Works from either state: from PAUSED it single-ticks, and from RUNNING
        it is effectively a no-op since the loop was going to tick anyway.

        Args:
            n (int): How many ticks to allow through. Default 1.

        Raises:
            ValueError: If ``n`` is not positive.
        """
        if n < 1:
            raise ValueError(f"n({n}) must be positive.")
        with self._steps_lock:
            self._steps_remaining += n

    def restart(self) -> None:
        """Reset the tree and the counters, ready for another :meth:`run`.

        Stops the root with INVALID so every active behavior runs its
        ``terminate()``, zeroes the tick and overrun counts, clears any pending
        shutdown request, and releases a hold. Setup is *not* repeated — the
        tree is already set up.
        """
        self._tree.root.stop(py_trees.common.Status.INVALID)
        self._ticks = 0
        self._overruns = 0
        self._last_overrun_log = None
        self._exit_code = EXIT_OK
        self._exit_code_set = False
        self._stop_requested.clear()
        self._pause_requested.clear()
        with self._steps_lock:
            self._steps_remaining = 0
        clear_shutdown_request()
        self._state = RunnerState.IDLE

    def _holding(self) -> bool:
        """Report whether the loop should sit still this iteration.

        Returns:
            bool: True when paused with no steps owed.
        """
        with self._steps_lock:
            if self._steps_remaining > 0:
                return False
        return self._pause_requested.is_set()

    def _consume_step(self) -> None:
        """Spend one owed step, if any are owed."""
        with self._steps_lock:
            if self._steps_remaining > 0:
                self._steps_remaining -= 1

    def _pause_slice(self) -> float:
        """How long a held loop sleeps before looking again.

        Returns:
            float: The pause slice, or the period when that is shorter, so a
            slow-rate runner does not become less responsive than a fast one.
        """
        if not self._period:
            return _PAUSE_SLICE
        return min(self._period, _PAUSE_SLICE)

    # -- Signals --------------------------------------------------------------

    def _install_signal_handlers(self) -> None:
        """Install handlers for the configured signals, where that is allowed.

        :func:`signal.signal` only works on the main thread, so a runner on a
        worker thread logs once at DEBUG and goes without. Wanting signals it
        cannot have is not a reason to refuse to run.
        """
        self._saved_handlers = {}
        if not self._signals:
            return
        if threading.current_thread() is not threading.main_thread():
            logger.debug("not on the main thread; running without signal handlers")
            return
        for sig in self._signals:
            try:
                self._saved_handlers[sig] = signal.signal(sig, self._handle_signal)
            except (ValueError, OSError):
                logger.debug(f"could not install a handler for {sig!r}", exc_info=True)

    def _handle_signal(self, signum: int, frame: object) -> None:
        """Turn a signal into a cooperative stop — or, the second time, an exit.

        The first signal requests a stop carrying ``128 + signum``, which is the
        shell convention: 130 for SIGINT, 143 for SIGTERM. A **second** signal
        restores the original handler and re-raises, so an operator can still
        escape a teardown that has hung on a socket or a thread join. Graceful
        shutdown that cannot itself be interrupted is worse than none.

        Args:
            signum (int): The signal number.
            frame: The interrupted stack frame. Unused.
        """
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = str(signum)
        if self._signal_seen:
            logger.warning(f"second {name} during shutdown; forcing exit")
            previous = self._saved_handlers.pop(signal.Signals(signum), signal.SIG_DFL)
            with contextlib.suppress(ValueError, OSError):
                signal.signal(signum, previous)  # type: ignore[arg-type]
            signal.raise_signal(signum)
            return
        self._signal_seen = True
        logger.info(f"{name} received; shutting down at the next tick boundary")
        self.stop(128 + signum)

    def _restore_signal_handlers(self) -> None:
        """Put back whatever handlers were installed before :meth:`run`."""
        for sig, handler in self._saved_handlers.items():
            with contextlib.suppress(ValueError, OSError):
                signal.signal(sig, handler)  # type: ignore[arg-type]
        self._saved_handlers = {}

    # -- Teardown -------------------------------------------------------------

    def _teardown(self) -> None:
        """Release everything the run held, in order, whatever went wrong.

        The order is the substance:

        1. ``root.stop(INVALID)`` — ``terminate()`` on every active behavior,
           releasing threads and handles.
        2. ``tree.shutdown()`` — ``py_trees``' per-node ``shutdown()``.
        3. Every :class:`Closeable` visitor, each in its own ``try``/``except``
           so one bad visitor cannot keep the rest open.
        4. Signal handlers restored.

        Behaviors release before visitors close, because a ``terminate()`` may
        emit a final status that should still reach a publisher or a trace.
        Closing the publisher first would silently drop it.
        """
        self._state = RunnerState.STOPPING
        try:
            try:
                self._tree.root.stop(py_trees.common.Status.INVALID)
            except Exception:
                logger.exception("root.stop(INVALID) raised during teardown")
            try:
                self._tree.shutdown()
            except Exception:
                logger.exception("tree.shutdown() raised during teardown")
            for visitor in list(self._tree.visitors):
                if not isinstance(visitor, Closeable):
                    continue
                try:
                    visitor.close()
                except Exception:
                    logger.exception(
                        f"closing visitor {type(visitor).__name__} raised; "
                        f"continuing with the rest"
                    )
        finally:
            self._restore_signal_handlers()
            self._state = RunnerState.STOPPED


__all__ = [
    "SHUTDOWN_KEY",
    "EXIT_OK",
    "EXIT_FAILURE",
    "EXIT_SETUP_FAILED",
    "EXIT_SOFTWARE",
    "Closeable",
    "ExitBehavior",
    "RaiseBehavior",
    "RequestShutdown",
    "RunnerState",
    "SetupError",
    "ShutdownRequest",
    "TreeRunner",
    "clear_shutdown_request",
]
