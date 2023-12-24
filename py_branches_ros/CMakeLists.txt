cmake_minimum_required(VERSION 3.0.2)
project(py_branches_ros)

find_package(catkin REQUIRED COMPONENTS
  py_branches
  roscpp
  rospy
  std_msgs
)

catkin_python_setup()

catkin_package(
)

include_directories(
  ${catkin_INCLUDE_DIRS}
)
