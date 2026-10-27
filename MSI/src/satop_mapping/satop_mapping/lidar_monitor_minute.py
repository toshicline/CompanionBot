"""Measure /scan delivery after warm-up; save ten fixed minute intervals.

Run with Python in a sourced ROS 2 Humble terminal. The sensor driver must
already be running. This observes messages and never changes /scan.
Maximum gaps include periods with no incoming messages. A gap crossing a
minute boundary is counted in both affected minutes. Results are finalized
at the end, because a later arrival can complete a cross-boundary gap.
"""

import csv
import math
import time
from datetime import datetime
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


class LidarMonitorMinute(Node):
    # Set up the LiDAR monitor and the test settings.
    def __init__(self):
        super().__init__('lidar_monitor_minute')
        self.declare_parameter('warmup_seconds', 120.0)
        self.declare_parameter('output_directory', '~/satop_test_results')
        self.warmup = float(self.get_parameter('warmup_seconds').value)
        if self.warmup < 0:
            raise ValueError('warmup_seconds must be nonnegative')
        self.output_dir = Path(str(self.get_parameter('output_directory').value)).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = self.output_dir / (
            'lidar_delivery_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.csv'
        )
        self.first_arrival = None
        self.test_start = None
        self.test_end = None
        self.last_arrival = None
        self.started = False
        self.done = False
        self.reported_minutes = 0
        self.counts = [0] * 10
        self.gaps = [0.0] * 10
        self.empty_scans = [0] * 10
        self.latest_valid = 0
        self.latest_total = 0
        self.subscription = self.create_subscription(
            LaserScan, '/scan', self.scan_callback, qos_profile_sensor_data
        )
        # A timer lets the test finish and detect silence even if scans stop.
        self.timer = self.create_timer(0.1, self.timer_callback)
        self.get_logger().info(
            f'Waiting for /scan. First scan starts {self.warmup:.0f} s warm-up; '
            'then a 10-minute delivery test.'
        )

    def record_gap(self, previous, current):
        "Measures time between scans. Ideally we want the maximum gap to no be more than 0.5 seconds"
        start = max(previous, self.test_start)
        end = min(current, self.test_end)
        if end <= start:
            return
        gap = end - start
        for index in range(10):
            left = self.test_start + index * 60.0
            right = left + 60.0
            if start < right and end > left:
                self.gaps[index] = max(self.gaps[index], gap)

    def scan_callback(self, msg):
        if self.done:
            return
        now = time.monotonic()
        if self.first_arrival is None:
            self.first_arrival = now
            self.test_start = now + self.warmup
            self.test_end = self.test_start + 600.0
            self.get_logger().info(
                f'LiDAR connected | Frame: {msg.header.frame_id} | '
                f'Range: {msg.range_min:.2f} to {msg.range_max:.2f} m'
            )
        if now >= self.test_start:
            previous = self.last_arrival if self.last_arrival is not None else self.test_start
            self.record_gap(previous, now)
            if now >= self.test_end:
                self.finish()
                return
            index = min(9, int((now - self.test_start) // 60.0))
            self.counts[index] += 1
            self.latest_total = len(msg.ranges)
            self.latest_valid = sum(
                math.isfinite(distance) and msg.range_min <= distance <= msg.range_max
                for distance in msg.ranges
            )
            if not msg.ranges:
                self.empty_scans[index] += 1
        self.last_arrival = now

    def timer_callback(self):
        if self.done or self.test_start is None:
            return
        now = time.monotonic()
        if now < self.test_start:
            return
        if not self.started:
            self.started = True
            self.get_logger().info('Warm-up complete. Measuring 10 minutes now.')
        previous = self.last_arrival if self.last_arrival is not None else self.test_start
        self.record_gap(previous, now)
        if now >= self.test_end:
            self.finish()
            return
        completed = int((now - self.test_start) // 60.0)
        while self.reported_minutes < completed:
            index = self.reported_minutes
            self.get_logger().info(
                f'Minute {index + 1}/10 | Rate: {self.counts[index] / 60.0:.3f} Hz | '
                f'Max gap so far: {self.gaps[index]:.3f} s | '
                f'Latest valid points: {self.latest_valid}/{self.latest_total}. '
                'Final gap results will be saved at test completion.'
            )
            self.reported_minutes += 1

    def finish(self):
        self.done = True
        self.timer.cancel()
        overall_pass = True
        with self.output_path.open('w', newline='') as output:
            writer = csv.writer(output)
            writer.writerow(['minute', 'scan_count', 'average_rate_hz',
                             'maximum_arrival_gap_s', 'empty_scan_count', 'delivery_result'])
            for index in range(10):
                rate = self.counts[index] / 60.0
                passed = rate >= 8.0 and self.gaps[index] <= 0.5
                overall_pass = overall_pass and passed
                status = 'PASS' if passed else 'FAIL'
                # Preserve full precision in the CSV for threshold comparisons.
                writer.writerow([index + 1, self.counts[index], rate,
                                 self.gaps[index], self.empty_scans[index], status])
                self.get_logger().info(
                    f'Minute {index + 1}/10 | {status} | Rate: {rate:.3f} Hz | '
                    f'Max gap: {self.gaps[index]:.6f} s'
                )
        self.get_logger().info(f'OVERALL DELIVERY RESULT: {"PASS" if overall_pass else "FAIL"}')
        self.get_logger().info(f'Results saved: {self.output_path}')
        if any(self.empty_scans):
            self.get_logger().warning(
                'Empty range arrays were received; inspect scan content separately. '
                'Delivery PASS only checks arrival rate and gaps.'
            )


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = LidarMonitorMinute()
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.2)
    except KeyboardInterrupt:
        if node is not None and not node.done:
            node.get_logger().warning('Test interrupted. No completed-test CSV was saved.')
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
