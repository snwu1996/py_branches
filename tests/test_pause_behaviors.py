#!/usr/bin/env python
import py_trees
import time
import numpy as np

from py_branches.pause import PauseUniform
from py_branches.pause import PauseSchedule
from py_branches.pause import CheckPauseSchedule


def test_pause_uniform():
	np.random.seed(0)
	pause_uniform = PauseUniform('pause_uniform', 0.2, 0.5)
	start_ts = time.time()
	while True:
		pause_uniform.tick_once()
		if pause_uniform.status == py_trees.common.Status.SUCCESS:
			break
		time.sleep(0.01)
	end_ts = time.time()
	t_elapse = end_ts - start_ts
	assert (0.2 < t_elapse < 0.5)
