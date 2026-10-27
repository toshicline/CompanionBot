import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration

from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def launch_setup(context):
    workspace = os.path.expanduser('~/CompanionBot/MSI')
    mode = LaunchConfiguration('mode').perform(context)

    if mode not in ('sensors', 'mapping', 'presentation'):
        raise ValueError(
            'mode must be sensors, mapping, or presentation'
        )

    slam_config = LaunchConfiguration('slam_params').perform(context)
    rviz_config = LaunchConfiguration('rviz_config').perform(context)
    map_name = LaunchConfiguration('map_name').perform(context)

    map_base = os.path.join(workspace, 'satop_maps', map_name)

    # Driver only: RViz is started separately below.
    lidar_launch = os.path.join(
        get_package_share_directory('sllidar_ros2'),
        'launch',
        'sllidar_c1_launch.py',
    )

    rover_urdf = os.path.join(
        get_package_share_directory('roverrobotics_description'),
        'urdf',
        'rover_2wd.urdf',
    )

    robot_description = ParameterValue(
        Command(['xacro ', rover_urdf]),
        value_type=str,
    )

    actions = [
        # 1. LiDAR driver: publishes /scan
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(lidar_launch)
        ),

        # 2. Filter: /scan -> /scan_filtered
        Node(
            package='laser_filters',
            executable='scan_to_scan_filter_chain',
            name='laser_filter_chain',
            parameters=[
                os.path.join(
                    workspace, 'config', 'laser_rear_filter.yaml'
                )
            ],
            remappings=[
                ('scan', '/scan'),
                ('scan_filtered', '/scan_filtered'),
            ],
            output='screen',
        ),

        # 3. LiDAR-based odometry
        Node(
            package='rf2o_laser_odometry',
            executable='rf2o_laser_odometry_node',
            name='rf2o_laser_odometry',
            parameters=[
                os.path.join(
                    workspace, 'config', 'rf2o_filtered.yaml'
                )
            ],
            output='screen',
        ),

        # 4. Scan/TF gate: publishes /scan_ready
        ExecuteProcess(
            cmd=[
                'python3',
                os.path.join(
                    workspace, 'scripts', 'scan_tf_gate.py'
                ),
            ],
            output='screen',
        ),

        # 5. Robot model and fixed joint transforms
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            parameters=[{
                'robot_description': robot_description,
                'use_sim_time': False,
            }],
            output='screen',
        ),

        # 6. Wheel joint positions for visualization
        Node(
            package='joint_state_publisher',
            executable='joint_state_publisher',
            name='joint_state_publisher',
            parameters=[{'use_sim_time': False}],
            output='screen',
        ),
    ]

    if mode == 'mapping':
        # Generate a new map.
        mapping_launch = os.path.join(
            get_package_share_directory('slam_toolbox'),
            'launch',
            'online_async_launch.py',
        )

        actions.append(
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(mapping_launch),
                launch_arguments={
                    'slam_params_file': slam_config,
                    'use_sim_time': 'false',
                }.items(),
            )
        )

    elif mode == 'presentation':
        # Check that both serialized pose-graph files exist.
        for extension in ('.posegraph', '.data'):
            filename = map_base + extension
            if not os.path.isfile(filename):
                raise FileNotFoundError(
                    f'Missing saved pose-graph file: {filename}'
                )

        # Localize against the original pose graph.
        # Later values override matching values in the mapping YAML.
        actions.append(
            Node(
                package='slam_toolbox',
                executable='localization_slam_toolbox_node',
                name='slam_toolbox',
                parameters=[
                    slam_config,
                    {
                        'use_sim_time': False,
                        'mode': 'localization',
                        'scan_topic': '/scan_ready',
                        'map_file_name': map_base,
                        'map_start_pose': [0.0, 0.0, 0.0],
                        'map_start_at_dock': False,
                        'enable_interactive_mode': False,
                    },
                ],
                output='screen',
            )
        )

        # Publish the edited occupancy map on a separate topic.
        actions.append(
            Node(
                package='nav2_map_server',
                executable='map_server',
                name='edited_map_server',
                parameters=[{
                    'use_sim_time': False,
                    'yaml_filename': map_base + '.yaml',
                    'frame_id': 'map',
                }],
                remappings=[
                    ('map', '/edited_map'),
                    ('map_updates', '/edited_map_updates'),
                ],
                output='screen',
            )
        )

        # Automatically configure and activate the edited map server.
        actions.append(
            Node(
                package='nav2_lifecycle_manager',
                executable='lifecycle_manager',
                name='presentation_lifecycle_manager',
                parameters=[{
                    'use_sim_time': False,
                    'autostart': True,
                    'node_names': ['edited_map_server'],
                }],
                output='screen',
            )
        )

    # The presentation configuration should use /edited_map.
    # In mapping mode, redirect that display to the live /map.
    rviz_remappings = []

    if mode == 'mapping':
        rviz_remappings = [
            ('/edited_map', '/map'),
            ('/edited_map_updates', '/map_updates'),
        ]

    actions.append(
        Node(
            package='rviz2',
            executable='rviz2',
            name='satop_rviz',
            arguments=[
                '-d', rviz_config,
                '-f', 'base_link' if mode == 'sensors' else 'map',
            ],
            parameters=[{'use_sim_time': False}],
            remappings=rviz_remappings,
            additional_env={
                'QT_QPA_PLATFORM': 'xcb',
                'LIBGL_ALWAYS_SOFTWARE': '1',
            },
            output='screen',
        )
    )

    return actions


def generate_launch_description():
    workspace = os.path.expanduser('~/CompanionBot/MSI')

    return LaunchDescription([
        DeclareLaunchArgument(
            'mode',
            default_value='sensors',
            description='sensors, mapping, or presentation',
        ),

        DeclareLaunchArgument(
            'slam_params',
            default_value=os.path.join(
                workspace, 'config', 'satop_slam_mapping.yaml'
            ),
        ),

        DeclareLaunchArgument(
            'rviz_config',
            default_value=os.path.join(
                workspace, 'config', 'presentation.rviz'
            ),
        ),

        DeclareLaunchArgument(
            'map_name',
            default_value='presentation_map',
            description='Saved map basename without extension',
        ),

        OpaqueFunction(function=launch_setup),
    ])