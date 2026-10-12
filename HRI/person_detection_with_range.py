import cv2
import logging
import math
from ultralytics import YOLO
from ultralytics.utils import LOGGER

# Set Ultralytics internal logger level to WARNING or ERROR
LOGGER.setLevel(logging.WARNING)

# Load model
model = YOLO("models/yolov8n-pose.pt")

# Set up OpenCV camera
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: Failed to open camera")
    exit()

print("\nCamera stream started. Press 'Q' to quit.\n")

# Common average human proportions (in meters)
AVG_HUMAN_PROPS = {
    "SHOULDER_TO_HIP":0.475,
    "HIP_TO_ANKLE":0.85
}

def draw_bbox(frame,box_dict,label,color=(0,0,255)):
    """Draw a bounding box around a target using box_dict

    Args:
        frame: OpenCV frame
        box_dict: Information about the bounding box
          Dictionary: {
                "id":box_count,
                "coords":(x1,y1,x2,y2),
                "area":area,
                "conf":conf,
                "object":box
            }
        label: Text above the bounding box
        color: Color for bbox and text (default is red)

    Returns: 
        None
    """

    # Get coords and confidence
    x1,y1,x2,y2 = box_dict["coords"]

    # Draw bounding box
    cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)

    # Draw label
    cv2.putText(frame,label,(x1,y1-10),cv2.FONT_HERSHEY_SIMPLEX,1,color,2)


def center_of_box(coords):

    x1,y1,x2,y2 = coords
    return (int(x1 + (x2-x1)/2), int(y1 + (y2-y1)/2))


def extract_usable_distances(keypoints):
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

    def get_side_distances(kpts_list, side_prefix):
        side_distances = []
        # Map name to position for quick lookup
        kpt_dict = {item["name"]: item["position"] for item in kpts_list}

        # Define key anatomical pairs to measure
        pairs = [
            ("shoulder", "hip"),
            ("hip", "ankle"),
            ("hip", "knee"),
            ("knee", "ankle"),
        ]

        for p1_name, p2_name in pairs:
            if p1_name in kpt_dict and p2_name in kpt_dict:
                pos1 = kpt_dict[p1_name]
                pos2 = kpt_dict[p2_name]

                # Euclidean distance in pixels
                dist = math.sqrt((pos2[0] - pos1[0]) ** 2 + (pos2[1] - pos1[1]) ** 2)

                from_name = f"{side_prefix}_{p1_name}"
                to_name = f"{side_prefix}_{p2_name}"

                side_distances.append((from_name, to_name, dist))

        return side_distances

    # Collect distances for both sides
    distances.extend(get_side_distances(left_kpts, "left"))
    distances.extend(get_side_distances(right_kpts, "right"))

    return distances


def estimate_range(distance_pixels,reference_distance_meters):
    """Estimate target range using shoulder to hip distance

    Args:
        distance_pixels: distance between two keypoints (ie, shoulder to hip)
        reference_distance_meters: the corresponding average distance in meters

    Returns: 
        int: range estimate (in meters)
    """

    f = 1300 # Vertical focal length of camera (pixels)
    H = reference_distance_meters # Real-world average distance from shoulder to hip (meters)
    P = distance_pixels # Shoulder to hip distance (pixels)

    Z = ( f * H ) / P

    return Z


def estimate_range_average(usable_distances):
    """Estimate target range using a list of distances
    
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
            ref_distance = AVG_HUMAN_PROPS["SHOULDER_TO_HIP"]
        elif "hip" in from_pt and "ankle" in to_pt:
            ref_distance = AVG_HUMAN_PROPS["HIP_TO_ANKLE"]
        else:
            continue  # Skip unmapped pairs

        z = estimate_range(p_dist, ref_distance)
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



# Main Loop
while True:

    # Capture video frame
    ret, frame = cap.read()
    if not ret:
        print("Error: Failed to get frame.")
        break

    # Feed frame into model
    results = model(frame,classes=[0],stream=True)

    ideal_target_position = (-1,-1)

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

        ideal_target = False # Whether or not the most confident box and the largest box are the same

        # Check if the largest and most confident are the same (this is the goal)
        if largest_bbox["id"] == confident_bbox["id"] and largest_bbox["id"] != -1:
            draw_bbox(frame,largest_bbox,f"Ideal target",color=(0,255,0))
            ideal_target = True

            ideal_target_position = center_of_box(largest_bbox["coords"])
            cv2.circle(frame,ideal_target_position,5,(255,0,0),-1)

        else: # otherwise, draw 2 boxes
            # Draw bounding box around largest box (if it exists)
            if largest_bbox["id"] != -1:
                draw_bbox(frame,largest_bbox,f"Largest area: {largest_bbox["area"]} (id={largest_bbox["id"]})")

            # Draw bounding box around most confident box (if it exists)
            if confident_bbox["id"] != -1:
                draw_bbox(frame,confident_bbox,f"Most conf: {confident_bbox["conf"]:.2f} (id={confident_bbox["id"]})")



        # Once we have an ideal target, we can do key point analysis to estimate distance
        if ideal_target:

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

            usable_kpts_dict = {}

            for point_name,point in kpt_dict.items():

                point_confidence = float(point[1])
                point_location = (int(point[0][0]),int(point[0][1]))

                if (point_confidence < 0.75):
                    continue
                else:
                    usable_kpts_dict[point_name] = point

                cv2.circle(frame,point_location,5,(0,0,255),5,-1)

            usable_distances = extract_usable_distances(usable_kpts_dict)

            range_estimate,range_points_used = estimate_range_average(usable_distances).values()

            if range_estimate > 0:
                print(f"Ideal target at ({ideal_target_position[0]},{ideal_target_position[1]})   Approx Range: {range_estimate:.2f}m ({range_points_used} points)")
            else:
                print(f"Ideal target at ({ideal_target_position[0]},{ideal_target_position[1]})")

    # Show the video output
    cv2.imshow("Person Detection Test Stream",frame)

    # Allow OpenCV to process window events and listen for exit key ('q')
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
