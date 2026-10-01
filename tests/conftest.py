#!/usr/bin/env python

import pytest

from py_branches.runtime import clear_shutdown_request


@pytest.fixture(autouse=True)
def _clean_shutdown_key():
    """Keep the reserved shutdown key out of the next test.

    ``py_trees``' blackboard is process-global, so a request filed by one test
    would otherwise stop the next test's runner on its first tick.
    """
    clear_shutdown_request()
    yield
    clear_shutdown_request()
