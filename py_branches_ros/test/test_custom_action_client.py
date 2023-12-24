#!/usr/bin/env python
import sys
import unittest
import rospy
import rostest
import actionlib
import actionlib_tutorials.msg
import py_trees
import py_trees_ros

from py_branches_ros.actions import CustomActionClient


ORDER = 5
SEQUENCE = (0,1,1,2,3,5)

class MyCustomActionClient(CustomActionClient):
    def __init__(self, name='my_custom_action_client'):
        goal = actionlib_tutorials.msg.FibonacciGoal(order=ORDER)
        super(MyCustomActionClient, self).__init__(name=name,
                                                   action_spec=actionlib_tutorials.msg.FibonacciAction,
                                                   action_goal=goal,
                                                   action_namespace='/fibonacci',
                                                   override_feedback_message_on_running='')

    def success_criteria(self, result):
        return result.sequence == SEQUENCE

class TestCustomActionClient(unittest.TestCase):
    def setUp(self):
        self._root = py_trees.Selector('root')   
        self._mcac = MyCustomActionClient()
        self._root.add_child(self._mcac)
        self._tree = py_trees_ros.trees.BehaviourTree(self._root)
        self._tree.setup(timeout=10.0)

    def tearDown(self):
        self._tree.blackboard_exchange.unregister_services()

    def test_custom_action_client_success(self):
        rate = rospy.Rate(10)
        while not rospy.is_shutdown():
            rate.sleep()

            self._tree.tick()
            success = self._mcac.status == py_trees.Status.SUCCESS and self._mcac.action_result is not None
            if success:
                rospy.loginfo(f'self._mcac.action_result: {self._mcac.action_result}')
                return

if __name__ == '__main__':
    rospy.init_node('test_custom_action_client')
    rostest.rosrun('py_branches_ros', 'test_custom_action_client', TestCustomActionClient, sys.argv)
