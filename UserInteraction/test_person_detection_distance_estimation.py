import cv2
import math
from ultralytics import YOLO

model = YOLO("models/yolov8n-pose.pt")

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: Failed to open camera")
    exit()

print("Camera stream started. Press 'Q' to quit.")

# Calculate midpoint between two points
def midpoint(p1,p2):
    x1,y1 = p1
    x2,y2 = p2

    return ((x2-x1)/2,(y2-y1)/2)


# Calculate the distance between the midpoints of two sets of 2 points
def distance_between_midpoints(point_set_1,point_set_2):
    # Calculate midpoint of each set
    mp1 = midpoint(point_set_1[0],point_set_1[1])
    mp2 = midpoint(point_set_2[0],point_set_2[1])

    x1,y1 = mp1
    x2,y2 = mp2

    return math.abs( math.sqrt( (x2-x1)**2 + (y2-y1)**2 ) )


def extract_usable_distances(data):
    """Calculates pairwise Euclidean distances for keypoints within the same body side.

    Args:
        data: Dictionary with 'left_side' and 'right_side' keys containing
          lists of tuples: [('point_name', np.array([x, y])), ...]

    Returns:
        Dictionary structured identically to the input, containing pairwise
        distances strictly within each side.

    Example output:
    {'left_side': [{'from': 'left_shoulder', 'to': 'left_hip', 'distance': 695.2643950993679}], 'right_side': [{'from': 'right_shoulder', 'to': 'right_hip', 'distance': 664.1978081900048}]}
    """
    result = {"left_side": [], "right_side": []}

    # Helper function to extract numerical coordinates
    def get_coords(pt):
        # Array/List/Tuple format: [x, y]
        return float(pt[0]), float(pt[1])

    for side in ["left_side", "right_side"]:
        points = data.get(side, [])
        n = len(points)

        # Compute pairwise distances for points on this side only
        for i in range(n):
            name1, pt1 = points[i]
            x1, y1 = get_coords(pt1)

            for j in range(i + 1, n):
                name2, pt2 = points[j]
                x2, y2 = get_coords(pt2)

                # Euclidean distance formula
                dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

                result[side].append(
                    {"from": name1, "to": name2, "distance": dist}
                )

    return result

def calculate_distance_shoulder_to_hip(shoulder_to_hip_distance):

    f = 1300 # Vertical focal length of camera (pixels)
    H = 0.475 # Real-world average distance from shoulder to hip (meters)
    P = shoulder_to_hip_distance # Shoulder to hip distance (pixels)

    Z = ( f * H ) / P

    return Z

def calculate_distance_hip_to_ankle(hip_to_ankle_distance):

    f = 1300 # Vertical focal length of camera (pixels)
    H = 0.85 # Real-world average distance from shoulder to hip (meters)
    P = hip_to_ankle_distance # Shoulder to hip distance (pixels)

    Z = ( f * H ) / P

    return Z








while True:

    # Capture video frame
    ret, frame = cap.read()
    if not ret:
        print("Error: Failed to get frame.")
        break

    # Feed frame into model
    results = model(frame,classes=[0],stream=True)

    # Iterate through model output
    for result in results:
        if result.keypoints != None:
            keypoints = result.keypoints.xy.cpu().numpy()
            keypoints_conf = result.keypoints.conf.cpu().numpy()

            for person_id in range(len(keypoints)):

                person_kpts = keypoints[person_id]
                conf_kpts = keypoints_conf[person_id]

                # Index	Keypoint Name	Anatomical Region
                # 0	    Nose	        Facial
                # 1	    Left Eye	    Facial
                # 2	    Right Eye	    Facial
                # 3	    Left Ear	    Facial
                # 4	    Right Ear	    Facial
                # 5	    Left Shoulder	Upper Body
                # 6	    Right Shoulder	Upper Body
                # 7	    Left Elbow	    Upper Body
                # 8	    Right Elbow	    Upper Body
                # 9	    Left Wrist	    Upper Body
                # 10	Right Wrist	    Upper Body
                # 11	Left Hip	    Lower Body
                # 12	Right Hip	    Lower Body
                # 13	Left Knee	    Lower Body
                # 14	Right Knee	    Lower Body
                # 15	Left Ankle	    Lower Body
                # 16	Right Ankle	    Lower Body

                keypoints = {
                    "left_shoulder":(person_kpts[5],conf_kpts[5]),
                    "right_shoulder":(person_kpts[6],conf_kpts[6]),
                    "left_hip":(person_kpts[11],conf_kpts[11]),
                    "right_hip":(person_kpts[12],conf_kpts[12]),
                    "left_knee":(person_kpts[13],conf_kpts[13]),
                    "right_knee":(person_kpts[14],conf_kpts[14]),
                    "left_ankle":(person_kpts[15],conf_kpts[15]),
                    "right_ankle":(person_kpts[16],conf_kpts[16]),
                }

                # points that have are visible, divided into left and right sides
                usable_points = {
                    "left_side":[], # ex: [ ("left_hip",(x,y)) , ...]
                    "right_side":[]
                }

                # extract usable points
                for name, (pt, conf) in keypoints.items():
                    x, y = int(pt[0]), int(pt[1])
                    conf = float(conf)

                    if (x > 0 and y > 0 and conf > 0.5):
                        if "left" in name:
                            usable_points["left_side"].append( (name,pt) )
                            cv2.circle(frame, (x, y), 8, (0, 0, 255), -1)
                        else:
                            usable_points["right_side"].append( (name,pt) )
                            cv2.circle(frame, (x, y), 8, (0, 0, 255), -1)

                distances = extract_usable_distances(usable_points)

                # --- PRINT ESTIMATED DISTANCES PER SIDE ---
                for side, side_distances in distances.items():
                    for item in side_distances:
                        from_pt = item["from"]
                        to_pt = item["to"]
                        p_dist = item["distance"]

                        # Process shoulder-to-hip measurements
                        if "shoulder" in from_pt and "hip" in to_pt:
                            # Calculate estimated distance in meters
                            z_meters = calculate_distance_shoulder_to_hip(p_dist)

                            print(
                                f"[{side}] {from_pt} -> {to_pt} | "
                                f"Pixel Dist: {p_dist:.1f}px | "
                                f"Est. Distance (Z): {z_meters:.2f} m"
                            )

                        if "hip" in from_pt and "ankle" in to_pt:
                            # Calculate estimated distance in meters
                            z_meters = calculate_distance_hip_to_ankle(p_dist)

                            print(
                                f"[{side}] {from_pt} -> {to_pt} | "
                                f"Pixel Dist: {p_dist:.1f}px | "
                                f"Est. Distance (Z): {z_meters:.2f} m"
                            )


                break # only calculate the first person

    # Show the video output
    cv2.imshow("Person Detection Test Stream",frame)

    # Allow OpenCV to process window events and listen for exit key ('q')
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
