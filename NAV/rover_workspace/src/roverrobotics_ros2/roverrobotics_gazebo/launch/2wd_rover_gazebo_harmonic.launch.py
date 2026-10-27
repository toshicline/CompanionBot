import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    # Create the launch configuration variables
    use_sim_time = LaunchConfiguration('use_sim_time')
    urdf = os.path.join(get_package_share_directory(
        'roverrobotics_description'), 'urdf', 'rover_2wd_harmonic.xacro')
    world = LaunchConfiguration('world')

    robot_desc = ParameterValue(Command(['xacro ', urdf]),
                                       value_type=str)
    
    declare_use_sim_time_cmd = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation (Gazebo) clock if true')
    
    declare_world_cmd = DeclareLaunchArgument(
        'world',
        default_value='slam_world.sdf',
        description='World file to use in Gazebo')
    
    gz_world_arg = PathJoinSubstitution([
        get_package_share_directory('roverrobotics_gazebo'), 'worlds', world])

    # Include the gz sim launch file  
    gz_sim_share = get_package_share_directory("ros_gz_sim")
    
    # # Restored to the clean original world launch, as Ogre 2 works perfectly on Harmonic
    # gz_sim = IncludeLaunchDescription(
    #     PythonLaunchDescriptionSource(os.path.join(gz_sim_share, "launch", "gz_sim.launch.py")),
    #     launch_arguments={
    #         "gz_args": gz_world_arg 
    #     }.items()
    # )

    # Force the '-s' flag right into the argument array so it never opens the GUI
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(gz_sim_share, "launch", "gz_sim.launch.py")),
        launch_arguments={
            "gz_args": ["-r -s ", gz_world_arg]
        }.items()
    )


    
    # Spawn Rover Robot
    gz_spawn_entity = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-topic", "/robot_description",
            "-name", "rover_miti",
            "-allow_renaming", "true",
            "-z", "0.1",
        ]
    )
    
    # Updated message mappings from ignition.msgs to gz.msgs for Gazebo Harmonic
    gz_ros2_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            "/cmd_vel@geometry_msgs/msg/Twist@gz.msgs.Twist",
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            "/odometry/wheels@nav_msgs/msg/Odometry@gz.msgs.Odometry",
            # "/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V", # it used to be this and it works but the <tf_topic>/tf_gazebo</tf_topic> in my xacro has to be set to this
            "/tf_gazebo@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V", # this is the new that sends messages to tf_gazebo instead of tf
            "/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model",
            "/scan@sensor_msgs/msg/LaserScan@gz.msgs.LaserScan",
            "/imu/data@sensor_msgs/msg/Imu@gz.msgs.IMU",
            
        ],
        
    )

    # Robot state publisher
    params = {'use_sim_time': use_sim_time, 'robot_description': robot_desc}
    start_robot_state_publisher_cmd = Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[params],
            arguments=[])

    ####################333 --- New Code for Map/World Visualization ---##############################
    
    # # Locate and parse obstacles xacro
    # obstacles_xacro = os.path.join(get_package_share_directory(
    #     'roverrobotics_description'), 'urdf', 'obstacles.urdf.xacro')
    
    # obstacles_desc = ParameterValue(Command(['xacro ', obstacles_xacro]), value_type=str)
    
    # # Stand up a secondary state publisher explicitly for the environment
    # params2 = {'use_sim_time': use_sim_time, 'robot_description': obstacles_desc}
    # start_obstacles_state_publisher_cmd = Node(
    #     package='robot_state_publisher',
    #     executable='robot_state_publisher',
    #     name='obstacles_state_publisher',
    #     output='screen',
    #     parameters=[params2],
    #     remappings=[('/robot_description', '/obstacles_description')] # avoids conflict with rover
    # )

    # # Bridge the gap between your rover's coordinate frame and the world frame
    # # Adjust 'odom' to match your robot's actual parent frame if using an EK/SLAM map node
    # world_to_odom_tf = Node(
    #     package='tf2_ros',
    #     executable='static_transform_publisher',
    #     name='world_to_odom_bridge',
    #     arguments=['0', '0', '0', '0', '0', '0', 'world', 'odom']
    # )

    
    ###################### END NEW CODE ########################################

    # Create the launch description and populate
    ld = LaunchDescription()




    # Add new environment visualization components
    # ld.add_action(start_obstacles_state_publisher_cmd)
    # ld.add_action(world_to_odom_tf)


    # Declare the launch options
    ld.add_action(declare_use_sim_time_cmd)
    ld.add_action(declare_world_cmd)

    # Launch Gazebo
    ld.add_action(gz_sim)
    ld.add_action(gz_spawn_entity)
    ld.add_action(gz_ros2_bridge)

    # Launch Robot State Publisher
    ld.add_action(start_robot_state_publisher_cmd)

    return ld
