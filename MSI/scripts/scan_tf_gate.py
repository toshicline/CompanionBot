

import time
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.time import Time
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener


class ScanTFGate(Node):

    def __init__(self):
        super().__init__('scan_tf_gate')

        # Receive and store transforms
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(
            self.tf_buffer, self
        )

        # Store incoming scans temporarily
        self.pending_scans = deque()
        self.max_wait = 2.0

        # Subscribe to filtered LiDAR data
        self.subscription = self.create_subscription(
            LaserScan,
            '/scan_filtered',
            self.scan_callback,
            qos_profile_sensor_data
        )

        # Publish scans once TF is available
        self.publisher = self.create_publisher(
            LaserScan,
            '/scan_ready',
            qos_profile_sensor_data
        )

        # Check pending scans every 20 ms
        self.timer = self.create_timer(
            0.02, self.check_scans
        )

        self.get_logger().info(
            'Scan TF gate started.'
        )

    def scan_callback(self, msg):
        # Avoid an unlimited backlog
        if len(self.pending_scans) >= 30:
            self.pending_scans.popleft()

        self.pending_scans.append(
            (time.monotonic(), msg)
        )

    def check_scans(self):
        now = time.monotonic()

        while self.pending_scans:
            received_at, scan = self.pending_scans[0]

            # Use the original scan timestamp
            scan_time = Time.from_msg(scan.header.stamp)

            # Check odometry-to-laser transform
            ready = self.tf_buffer.can_transform(
                'odom',
                scan.header.frame_id,
                scan_time
            )

            if ready:
                self.publisher.publish(scan)
                self.pending_scans.popleft()

            elif now - received_at > self.max_wait:
                self.get_logger().warning(
                    'Dropping scan: TF unavailable'
                )
                self.pending_scans.popleft()

            else:
                # Wait for the next timer check
                break


def main(args=None):
    rclpy.init(args=args)
    node = ScanTFGate()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
