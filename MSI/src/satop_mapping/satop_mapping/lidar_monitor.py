import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


class LidarMonitor(Node):

    def __init__(self):
        super().__init__('lidar_monitor')

        # Subscribe to the LiDAR scan topic
        self.subscription = self.create_subscription(
            LaserScan,
            '/scan',
            self.scan_callback,
            qos_profile_sensor_data
        )

        # Variables used to monitor scan performance
        self.message_count = 0
        self.window_start = time.monotonic()
        self.last_scan_time = None
        self.max_gap = 0.0
        self.first_scan = True

        self.get_logger().info(
            'LiDAR monitor started. Waiting for /scan...'
        )


    def scan_callback(self, msg):

        current_time = time.monotonic()

        # -----------------------------------
        # Measure time between scans
        # -----------------------------------

        if self.last_scan_time is not None:
            scan_gap = current_time - self.last_scan_time

            if scan_gap > self.max_gap:
                self.max_gap = scan_gap

        self.last_scan_time = current_time
        self.message_count += 1


        # -----------------------------------
        # Show LiDAR information once
        # -----------------------------------

        if self.first_scan:
            self.get_logger().info(
                f'LiDAR connected | '
                f'Frame: {msg.header.frame_id} | '
                f'Range: {msg.range_min:.2f} m to '
                f'{msg.range_max:.2f} m'
            )

            self.first_scan = False


        # -----------------------------------
        # Filter invalid measurements
        # -----------------------------------

        valid_ranges = [
            distance
            for distance in msg.ranges
            if math.isfinite(distance)
            and msg.range_min <= distance <= msg.range_max
        ]

        total_points = len(msg.ranges)
        valid_points = len(valid_ranges)
        invalid_points = total_points - valid_points


        # -----------------------------------
        # Report status about once per second
        # -----------------------------------

        elapsed_time = current_time - self.window_start

        if elapsed_time >= 1.0:

            scan_rate = self.message_count / elapsed_time

            if valid_ranges:
                closest_distance = min(valid_ranges)
                farthest_distance = max(valid_ranges)
            else:
                closest_distance = 0.0
                farthest_distance = 0.0


            # Check SATOP LiDAR requirements
            rate_ok = scan_rate >= 8.0
            gap_ok = self.max_gap <= 0.5

            if rate_ok and gap_ok:
                status = 'PASS'
            else:
                status = 'WARN'


            message = (
                f'{status} | '
                f'Rate: {scan_rate:.2f} Hz | '
                f'Max gap: {self.max_gap:.3f} s | '
                f'Valid: {valid_points}/{total_points} | '
                f'Invalid: {invalid_points} | '
                f'Closest: {closest_distance:.2f} m | '
                f'Farthest: {farthest_distance:.2f} m'
            )


            if status == 'PASS':
                self.get_logger().info(message)
            else:
                self.get_logger().warning(message)


            # Reset values for the next reporting window
            self.message_count = 0
            self.window_start = current_time
            self.max_gap = 0.0


def main(args=None):

    rclpy.init(args=args)

    node = LidarMonitor()

    rclpy.spin(node)

    node.destroy_node()

    rclpy.shutdown()


if __name__ == '__main__':
    main()