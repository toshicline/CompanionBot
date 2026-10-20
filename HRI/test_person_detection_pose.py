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

                for name, (pt, conf) in keypoints.items():
                    x, y = int(pt[0]), int(pt[1])
                    conf_val = float(conf)

                    # Only display keypoints that pass a visibility/confidence threshold
                    if x > 0 and y > 0 and conf > 0.5:
                        # Draw keypoint circle marker
                        cv2.circle(frame, (x, y), 4, (0, 0, 255), -1)

                        # Format label text (e.g., "nose 0.89")
                        label = f"{name} {conf_val:.2f}"

                        # Draw text offset slightly from the point
                        cv2.putText(frame,label,(x + 5, y - 5),cv2.FONT_HERSHEY_SIMPLEX,1,(255, 255, 255),1)



                break # only show the first person

    # Show the video output
    cv2.imshow("Person Detection Test Stream",frame)

    # Allow OpenCV to process window events and listen for exit key ('q')
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
