
import argparse

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from geometry_msgs.msg import Point
from visualization_msgs.msg import Marker


class VirtualBoundary(Node):
    def __init__(self, x_min, x_max, y_min, y_max):
        super().__init__('satop_virtual_boundary')

        qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL
        )

        self.publisher = self.create_publisher(
            Marker, '/satop_boundary', qos
        )

        self.corners = [
            (x_min, y_min),
            (x_max, y_min),
            (x_max, y_max),
            (x_min, y_max),
            (x_min, y_min)
        ]

        self.timer = self.create_timer(
            1.0, self.publish_boundary
        )
        self.publish_boundary()

    def publish_boundary(self):
        marker = Marker()
        marker.header.frame_id = 'odom'
        marker.header.stamp = self.get_clock().now().to_msg()

        marker.ns = 'satop_boundary'
        marker.id = 0
        marker.type = Marker.LINE_STRIP
        marker.action = Marker.ADD
        marker.pose.orientation.w = 1.0

        marker.scale.x = 0.08

        # Yellow so the virtual boundary is easy to identify
        marker.color.r = 1.0
        marker.color.g = 0.8
        marker.color.b = 0.0
        marker.color.a = 1.0

        marker.frame_locked = True

        marker.points = [
            Point(x=float(x), y=float(y), z=0.05)
            for x, y in self.corners
        ]

        self.publisher.publish(marker)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--x-min', type=float, required=True)
    parser.add_argument('--x-max', type=float, required=True)
    parser.add_argument('--y-min', type=float, required=True)
    parser.add_argument('--y-max', type=float, required=True)
    args = parser.parse_args()

    if args.x_min >= args.x_max or args.y_min >= args.y_max:
        parser.error('Minimum coordinates must be less than maximums.')

    rclpy.init()
    node = VirtualBoundary(
        args.x_min, args.x_max,
        args.y_min, args.y_max
    )

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
