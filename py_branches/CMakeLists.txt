cmake_minimum_required(VERSION 3.0.2)
project(py_branches)


find_package(catkin REQUIRED COMPONENTS
  roscpp
  rospy
  std_msgs
  py_trees_ros
)

catkin_python_setup()

catkin_package(
)

include_directories(
  ${catkin_INCLUDE_DIRS}
)
