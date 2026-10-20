import math
import statistics

import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


def main():
    rclpy.init()
    node = rclpy.create_node('lidar_distance_validation')

    readings = []
    scan_count = 0
    total_scans = 30

    # Select the beam toward your board: 180 degrees in laser frame.
    forward_angle = math.pi

    def scan_callback(msg):
        nonlocal scan_count

        if not msg.ranges:
            print('Empty scan — skipping')
            return

        # Find the beam nearest the selected angle.
        index = min(
            range(len(msg.ranges)),
            key=lambda i: abs(math.atan2(
                math.sin(
                    msg.angle_min
                    + i * msg.angle_increment
                    - forward_angle
                ),
                math.cos(
                    msg.angle_min
                    + i * msg.angle_increment
                    - forward_angle
                )
            ))
        )

        distance = msg.ranges[index]
        scan_count += 1

        valid = (
            math.isfinite(distance)
            and msg.range_min <= distance <= msg.range_max
        )

        if valid:
            readings.append(distance)
            print(
                f'Scan {scan_count}/{total_scans}: '
                f'{distance:.3f} m'
            )
        else:
            print(
                f'Scan {scan_count}/{total_scans}: '
                f'invalid ({distance})'
            )

    subscription = node.create_subscription(
        LaserScan,
        '/scan',
        scan_callback,
        qos_profile_sensor_data
    )

    print('Waiting for live /scan...')

    try:
        while scan_count < total_scans:
            rclpy.spin_once(node, timeout_sec=1.0)

        print(f'\nValid readings: {len(readings)}/{total_scans}')

        if readings:
            print(
                f'Mean distance: '
                f'{statistics.mean(readings):.3f} m'
            )
            print(f'Minimum: {min(readings):.3f} m')
            print(f'Maximum: {max(readings):.3f} m')
        else:
            print('No valid readings received.')

    except KeyboardInterrupt:
        print('\nTest stopped.')

    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
