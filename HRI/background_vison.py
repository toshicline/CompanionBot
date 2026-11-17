import cv2
import logging
import math
import threading
import time
from ultralytics import YOLO
from ultralytics.utils import LOGGER


class PersonDetectionThread(threading.Thread):

    def __init__(self,camera_id=0):
        super().__init__()
        self.daemon = True

        # Constants
        self.joint_confidence_threshold = 0.75 # The confidence value required to consider a joint keypoint present
        self.camera_video_height = 1080
        self.camera_vertical_fov = 48.8 # Camera vertical FOV (in degrees)
        self.camera_horizontal_fov = 0 # Camera horizontal FOV (in degrees)

        # Set Ultralytics internal logger level to WARNING or ERROR
        LOGGER.setLevel(logging.WARNING)

        # Load model
        self.model = YOLO("models/yolov8n-pose.pt")

        # Set up OpenCV camera
        self.cap = cv2.VideoCapture(0)

        if not self.cap.isOpened():
            print("Error: Failed to open camera")
            exit()

        # Common average human proportions (in meters)
        self.avg_human_props = {
            "SHOULDER_TO_HIP": 0.475,
            "HIP_TO_KNEE": 0.44,
            "KNEE_TO_ANKLE": 0.41,
            "HIP_TO_ANKLE": 0.85,
        }

        self.lock = threading.Lock()
        self.person_visible = False
        self.target_position = (-1,-1) # Target x,y (pixels)
        self.range_estimate = -1
        self.range_points_used = 0
        self.yaw = -1
        self.running = True

    def get_focal_length(self,image_height, vfov_deg):
        """Return the vertical focal length (in pixels)
        
        Args:
            image_height: height of video frame
            vfov_deg: vertical field of view of camera (degree)

        Returns:
            float: focal length
        """

        vfov_rad = math.radians(vfov_deg)
        return image_height / (2 * math.tan(vfov_rad / 2))

    def calculate_rotation_angle(self,target_x, image_width, range_estimate, hfov_deg=60.0):
        """Calculates the 1D rotation angle from the rover to the target 
        using a geometric triangle formed by the range estimate and horizontal pixel offset.
        
        Args:
            target_x (float): Pixel x-coordinate of the target center.
            image_width (float): Total width of the camera frame in pixels.
            range_estimate (float): Estimated range (Z) to the target in meters.
            hfov_deg (float): Horizontal Field of View of the camera in degrees.
            
        Returns:
            float: Rotation angle in degrees (positive = target is to the right, negative = to the left).
        """
        if range_estimate <= 0 or image_width <= 0 or hfov_deg <= 0:
            return 0.0

        center_x = image_width / 2.0
        pixel_offset = target_x - center_x
        
        # Derive horizontal focal length in pixels from HFOV and image width
        hfov_rad = math.radians(hfov_deg)
        tan_half_fov = math.tan(hfov_rad / 2.0)
        
        if tan_half_fov == 0:
            return 0.0
            
        focal_length_x = center_x / tan_half_fov
        
        if focal_length_x == 0:
            return 0.0
        
        # Convert pixel offset to a real-world lateral offset (X_offset) in meters
        lateral_offset_m = (pixel_offset / focal_length_x) * range_estimate
        
        # Use right-triangle trigonometry (arctan) to find the angle
        angle_rad = math.atan2(lateral_offset_m, range_estimate)
        
        return math.degrees(angle_rad)


    def center_of_box(self,coords):
        """Get the center point of a rectangle given its 4 corner coordinates
        
        Args:
            coords: list/tuple of coordinates as (x1,y1,x2,y2)

        Returns:
            (int,int): (x,y)
        """

        x1,y1,x2,y2 = coords
        return (int(x1 + (x2-x1)/2), int(y1 + (y2-y1)/2))


    def extract_usable_distances(self,keypoints):
        """Extract the usable distances (ie right shoulder to right hip) in pixels from a list of keypoints

        Args:
            keypoints: information about the keypoints on an ideal target
                Dictionary: {
                    "left_shoulder": ((x,y), 0.95),
                    ...
                }

        Returns:
            list: list of tuples with the format: (from_point,to_point,distance_pixels)
        """

        left_kpts = []
        right_kpts = []

        # Split into left and right side keypoints
        for point_name,point_info in keypoints.items():
            if "right" in point_name:
                right_kpts.append({
                    "name":point_name.replace("right_",""),
                    "position":(int(point_info[0][0]),int(point_info[0][1])),
                    "confidence":float(point_info[1])
                })
            else:
                left_kpts.append({
                    "name":point_name.replace("left_",""),
                    "position":(int(point_info[0][0]),int(point_info[0][1])),
                    "confidence":float(point_info[1])
                })

        distances = []

        # Helper function to get distances per side
        def get_side_distances(kpts_list, side_prefix):
            side_distances = []
            # Map name to position for quick lookup
            kpt_dict = {item["name"]: item["position"] for item in kpts_list}

            # Define key anatomical pairs to measure
            pairs = [
                ("shoulder", "hip"),
                ("hip", "knee"),
                ("knee", "ankle"),
                ("hip", "ankle"),
            ]

            # loop through each of the pairs defined above and see if a distance for that pair exists
            for p1_name, p2_name in pairs:
                if p1_name in kpt_dict and p2_name in kpt_dict:
                    pos1 = kpt_dict[p1_name]
                    pos2 = kpt_dict[p2_name]

                    pos1_x,pos1_y = pos1
                    pos2_x,pos2_y = pos2

                    # Euclidean distance in pixels
                    dist = math.sqrt((pos2_x - pos1_x) ** 2 + (pos2_y - pos1_y) ** 2)

                    from_name = f"{side_prefix}_{p1_name}"
                    to_name = f"{side_prefix}_{p2_name}"

                    side_distances.append((from_name, to_name, dist))

            return side_distances

        # Collect distances for both sides
        distances.extend(get_side_distances(left_kpts, "left"))
        distances.extend(get_side_distances(right_kpts, "right"))

        return distances


    def estimate_range(self,distance_pixels,reference_distance_meters):
        """Estimate target range using shoulder to hip distance

        Args:
            distance_pixels: distance between two keypoints (ie, shoulder to hip)
            reference_distance_meters: the corresponding average distance in meters

        Returns: 
            int: range estimate (in meters)
        """

        f = self.get_focal_length(self.camera_video_height,self.camera_vertical_fov) # Vertical focal length of camera (pixels)
        H = reference_distance_meters # Real-world average distance from shoulder to hip (meters)
        P = distance_pixels # Shoulder to hip distance (pixels)

        Z = ( f * H ) / P

        return Z


    def estimate_range_average(self,usable_distances):
        """Estimate target range using a list of distances (averages all the distances together)
        
        Args:
            usable_distances: list of distances between keypoints (in pixels)
                [('left_shoulder', 'left_hip', 718.4184017687743), ('right_shoulder', 'right_hip', 694.050430444359), ...]
        
        Returns:
            dict: {
                "estimate": range estimate (in meters)
                "points_used": number of points used in estimate
            }
        """
        range_estimates = []

        for from_pt, to_pt, p_dist in usable_distances:

            # Map keypoint relationship to the correct constant from AVG_HUMAN_PROPS
            if "shoulder" in from_pt and "hip" in to_pt:
                ref_distance = self.avg_human_props["SHOULDER_TO_HIP"]
            elif "hip" in from_pt and "knee" in to_pt:
                ref_distance = self.avg_human_props["HIP_TO_KNEE"]
            elif "knee" in from_pt and "ankle" in to_pt:
                ref_distance = self.avg_human_props["KNEE_TO_ANKLE"]
            elif "hip" in from_pt and "ankle" in to_pt:
                ref_distance = self.avg_human_props["HIP_TO_ANKLE"]
            else:
                continue  # Skip unmapped pairs

            z = self.estimate_range(p_dist, ref_distance)
            range_estimates.append(z)

        # Return the average range, or -1 if no valid pairs were found
        if not range_estimates:
            return {
                    "estimate":-1,
                    "points_used":0
                }
        
        return {
            "estimate":sum(range_estimates) / len(range_estimates),
            "points_used":len(range_estimates) * 2
        }


    def run(self):
                
        while self.running:

            # Capture video frame
            ret, frame = self.cap.read()
            if not ret:
                print("Error: Failed to get frame.")
                break

            # Feed frame into model
            results = self.model(frame,classes=[0],stream=True)

            # Setup position of ideal target
            found_target = False
            t_pos = (-1,-1)
            r_est = -1.0
            r_pts = 0

            # Iterate through model output
            for result in results:

                # Get all the targets
                boxes = result.boxes

                # Largest bounding box by area
                largest_bbox = {
                    "id":-1,
                    "coords":(0,0,0,0),
                    "area":0,
                    "conf":0,
                    "object":None
                }

                # Bounding box with highest confidence
                confident_bbox = {
                    "id":-1,
                    "coords":(0,0,0,0),
                    "area":0,
                    "conf":0,
                    "object":None
                }

                box_count = 0
                for box in boxes:
                    # Convert bounding box to ints
                    x1,y1,x2,y2 = box.xyxy[0].cpu().numpy().astype(int)

                    # Extract confidence
                    conf = float(box.conf[0].cpu().numpy())

                    # Calculate box area
                    width = x2-x1
                    height = y2-y1
                    area = width*height

                    # If this is the biggest box so far, update largest bounding box
                    if area > largest_bbox["area"]:
                        largest_bbox = {
                            "id":box_count,
                            "coords":(x1,y1,x2,y2),
                            "area":area,
                            "conf":conf,
                            "object":box
                        }

                    # If this is the most confident box so far, update the most confident box
                    if conf > confident_bbox["conf"]:
                        confident_bbox = {
                            "id":box_count,
                            "coords":(x1,y1,x2,y2),
                            "area":area,
                            "conf":conf,
                            "object":box
                        }

                    # update ID
                    box_count += 1

                # Check if the largest and most confident are the same (this is the goal)
                if largest_bbox["id"] == confident_bbox["id"] and largest_bbox["id"] != -1:
                    found_target = True

                    t_pos = self.center_of_box(largest_bbox["coords"])

                # Once we have an ideal target, we can do key point analysis to estimate distance
                if found_target:

                    target_id = largest_bbox["id"]

                    # Extract the target person's keypoints & confidences
                    target_kpts = result.keypoints.xy[target_id].cpu().numpy()
                    target_confs = result.keypoints.conf[target_id].cpu().numpy()

                    # Map the relevant joints for distance estimation
                    kpt_dict = {
                        "left_shoulder": (target_kpts[5], target_confs[5]),
                        "right_shoulder": (target_kpts[6], target_confs[6]),
                        "left_hip": (target_kpts[11], target_confs[11]),
                        "right_hip": (target_kpts[12], target_confs[12]),
                        "left_knee": (target_kpts[13], target_confs[13]),
                        "right_knee": (target_kpts[14], target_confs[14]),
                        "left_ankle": (target_kpts[15], target_confs[15]),
                        "right_ankle": (target_kpts[16], target_confs[16]),
                    }

                    # From the dictionary above, create an identical one but only with points that are visible and above JOINT_CONFIDENCE_THRESHOLD
                    usable_kpts_dict = {}

                    # Iterate through each keypoint and add to usable_kpts_dict if it is present in the frame (and draw a circle on it)
                    for point_name,point in kpt_dict.items():

                        point_confidence = float(point[1])
                        point_location = (int(point[0][0]),int(point[0][1]))

                        if (point_confidence < self.joint_confidence_threshold):
                            continue
                        else:
                            usable_kpts_dict[point_name] = point

                        cv2.circle(frame,point_location,5,(0,0,255),5,-1)

                    # From usable_kpts_dict, get the distances that can be used to estimate range
                    usable_distances = self.extract_usable_distances(usable_kpts_dict)

                    # Estimate the range using the distances from above (and get how many points the estimate is based off of)
                    r_est,r_pts = self.estimate_range_average(usable_distances).values()
                    break

            with self.lock:
                self.person_visible = found_target
                self.target_position = t_pos
                self.range_estimate = r_est
                self.range_points_used = r_pts
                self.yaw = self.calculate_rotation_angle(self.target_position[0],1080,self.range_estimate)

            time.sleep(0.01)

    def get_tracking_data(self):
        with self.lock:
            return {
                "visible": self.person_visible,
                "position": self.target_position,
                "range": self.range_estimate,
                "points": self.range_points_used,
                "yaw": self.yaw
            }

    def stop(self):
        self.running = False
        self.cap.release()
