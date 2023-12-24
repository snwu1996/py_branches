#!/usr/bin/env python3
import rospy
import py_trees
from abc import abstractmethod
from py_trees_ros.actions import ActionClient


class CustomActionClient(ActionClient):
    def __init__(self, 
                 name='Action Client', 
                 action_spec=None, 
                 action_goal=None, 
                 action_namespace='/action',
                 override_feedback_message_on_running=''):
        super_args = (name, action_spec, action_goal, action_namespace, override_feedback_message_on_running)
        super(CustomActionClient, self).__init__(*super_args)

    @abstractmethod
    def success_criteria(self, action_result):
        raise Exception('success_criteria method not implemented')

    def initialise(self):
        super(CustomActionClient, self).initialise()
        self.action_result = None

    def update(self):
        super_status = super(CustomActionClient, self).update()
        if super_status == py_trees.Status.RUNNING or super_status == py_trees.Status.INVALID:
            return super_status

        self.action_result = self.action_client.get_result()
        if self.action_result is None or not self.success_criteria(self.action_result):
            return py_trees.Status.FAILURE
        else:
            return py_trees.Status.SUCCESS
