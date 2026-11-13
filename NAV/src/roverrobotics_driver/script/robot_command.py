#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

class NavCommandNode(Node):
    def __init__(self):
        super().__init__('nav_command_node')
        
        # Initialize the Nav2 BasicNavigator
        self.navigator = BasicNavigator()
        
        # Define your named locations (x, y, z_orientation, w_orientation)
        self.locations = {
            'origin': (0.0, 0.0, 0.0, 1.0),
            'top right' : (8.3 9.3 0 0),
            'middle right' : (6.6 -1.58 0 0),
            'bottom right' : (5.3 -7.44 0 0),
            'top left' : (-10.6 4.98 0 0),
            'bottom left' : (-6.73 -4.07 0 0),
        }

        # Subscribe to your custom command topic
        self.subscription = self.create_subscription(
            String,
            '/robot_command',
            self.command_callback,
            10
        )
        
        # Timer to monitor navigation progress without blocking callbacks
        self.timer = self.create_timer(0.5, self.check_status)
        self.is_navigating = False
        self.get_logger().info('NavCommandNode ready. Send commands to /robot_command.')

    def create_pose(self, x, y, z, w):
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.navigator.get_clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.orientation.z = z
        pose.pose.orientation.w = w
        return pose

    def command_callback(self, msg):
        cmd = msg.data.strip().lower()
        
        if cmd == 'cancel':
            self.get_logger().info('Canceling current navigation task...')
            self.navigator.cancelTask()
            self.is_navigating = False
            return

        if cmd in self.locations:
            x, y, z, w = self.locations[cmd]
            goal_pose = self.create_pose(x, y, z, w)
            
            self.get_logger().info(f'Navigating to {cmd} ({x}, {y})...')
            self.navigator.goToPose(goal_pose)
            self.is_navigating = True
        else:
            self.get_logger().warn(f'Unknown command: "{cmd}". Valid: {list(self.locations.keys())}')

    def check_status(self):
        if not self.is_navigating:
            return

        if self.navigator.isTaskComplete():
            self.is_navigating = False
            result = self.navigator.getResult()
            if result == TaskResult.SUCCEEDED:
                self.get_logger().info('Goal reached successfully!')
            elif result == TaskResult.CANCELED:
                self.get_logger().info('Goal was canceled.')
            elif result == TaskResult.FAILED:
                self.get_logger().error('Goal failed!')

def main(args=None):
    rclpy.init(args=args)
    node = NavCommandNode()
    
    # Note: If your node starts before Nav2, uncomment the line below:
    # node.navigator.waitUntilNav2Active(localizer='slam_toolbox')
    
    rclpy.spin(node)
    node.destroy_node()
    node.navigator.lifecycleShutdown()
    rclpy.shutdown()

if __name__ == '__main__':
    main()

