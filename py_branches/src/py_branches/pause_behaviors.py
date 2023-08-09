#!/usr/bin/env python3
import rospy
import py_trees
import datetime
import random
import yaml
import os
import numpy as np


HOUR2SEC = 3600
MIN2SEC = 60


class PauseUniform(py_trees.behaviour.Behaviour):
    def __init__(self, name: str, low: float, high: float):
        super(PauseUniform, self).__init__(name=name)
        self._high = high
        self._low = low

    def initialise(self):
        self._pause_t = np.random.uniform(self._low, self._high)
        self._start_t = rospy.Time.now()

    def update(self):
        t_elapse = (rospy.Time.now() - self._start_t).to_sec()
        if t_elapse < self._pause_t:
            return py_trees.Status.RUNNING
        else:
            return py_trees.Status.SUCCESS

def load_schedule_file(schedule_filepath: str):
    assert os.path.isfile(schedule_filepath), f'schedule_filepath: {schedule_filepath} is not a valid file'
    
    with open(schedule_filepath, 'r') as schedule_file:
        schedule_raw = yaml.safe_load(schedule_file)

    schedule = []
    for schedule_element_raw in schedule_raw:
        start_pause_time = datetime.datetime.strptime(schedule_element_raw['start_pause_time'], '%H:%M:%S').time()
        stop_pause_time = datetime.datetime.strptime(schedule_element_raw['stop_pause_time'], '%H:%M:%S').time()
        variance_time = datetime.datetime.strptime(schedule_element_raw['variance'], '%H:%M:%S').time()
        schedule.append({'start_pause_time': start_pause_time,
                         'stop_pause_time': stop_pause_time,
                         'variance_time': variance_time,
                         'logout_plus_variance_time': add_variance_to_datetime_time(start_pause_time, variance_time),
                         'login_plus_variance_time': add_variance_to_datetime_time(stop_pause_time, variance_time)})
    return schedule

class CheckPauseSchedule(py_trees.behaviour.Behaviour):
    def __init__(self, name: str, schedule):
        self._schedule = schedule
        self._last_schedule_idx = None
        super(CheckPauseSchedule, self).__init__(name=name)

    def update(self):
        now_time = datetime.datetime.now().time()
        for idx, schedule_element in enumerate(self._schedule):
            if idx == self._last_schedule_idx:
                continue

            logout = schedule_element['logout_plus_variance_time']
            login = schedule_element['login_plus_variance_time']
            if (logout < login and logout < now_time < login) or \
               (logout > login and (now_time > logout or now_time < login)): 
                self._last_schedule_idx = idx
                return py_trees.Status.SUCCESS
        return py_trees.Status.FAILURE

def datetime_time_to_sec(time):
    sec = time.hour*HOUR2SEC+time.minute*MIN2SEC+time.second
    return sec
    
def add_variance_to_datetime_time(time, variance_time):
    variance_sec = datetime_time_to_sec(variance_time)
    variance_timedelta = datetime.timedelta(seconds=random.uniform(0.0, variance_sec))
    time_to_datetime = datetime.datetime.combine(datetime.date.today(), time)
    time_with_variance = (time_to_datetime + variance_timedelta).time()
    return time_with_variance

class PauseSchedule(py_trees.behaviour.Behaviour):
    def __init__(self, name: str, schedule):
        self._schedule = schedule
        super(PauseSchedule, self).__init__(name=name)

    def initialise(self):
        super().initialise()
        self._t_wait = None
        self._t_start = None
        now_time = datetime.datetime.now().time()
        for schedule_element in self._schedule:
            logout = schedule_element['logout_plus_variance_time']
            login = schedule_element['login_plus_variance_time']
            variance = schedule_element['variance_time']
            if (logout < login and logout < now_time < login) or \
               (logout > login and (now_time > logout or now_time < login)): 
                if now_time < login:
                    self._t_wait = datetime_time_to_sec(login) - \
                                   datetime_time_to_sec(now_time)
                else:
                    self._t_wait = datetime_time_to_sec(datetime.time(23, 59, 59)) + 1 - \
                                   datetime_time_to_sec(now_time) + \
                                   datetime_time_to_sec(login)
                self._t_start = rospy.Time.now()
                rospy.loginfo(f'Wait has been scheduled for  {self._t_wait:.3f} sec')
                schedule_element['logout_plus_variance_time'] = \
                    add_variance_to_datetime_time(schedule_element['start_pause_time'], variance)
                schedule_element['login_plus_variance_time'] = \
                    add_variance_to_datetime_time(schedule_element['stop_pause_time'], variance)
                rospy.loginfo(f'new logout_plus_variance_time: {schedule_element["logout_plus_variance_time"]}')
                rospy.loginfo(f'new login_plus_variance_time: {schedule_element["login_plus_variance_time"]}')
                break

    def update(self):
        if self._t_wait is None:
            return py_trees.Status.SUCCESS

        t_elapse = (rospy.Time.now() - self._t_start).to_sec()
        if t_elapse < self._t_wait:
            return py_trees.Status.RUNNING
        else:
            return py_trees.Status.SUCCESS