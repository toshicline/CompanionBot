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

            for person_kpts in keypoints:

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
                    "nose":person_kpts[0],
                    "left_eye":person_kpts[1],
                    "right_eye":person_kpts[2],
                    "left_shoulder":person_kpts[5],
                    "right_shoulder":person_kpts[6],
                    "left_hip":person_kpts[11],
                    "right_hip":person_kpts[12],
                    "left_knee":person_kpts[13],
                    "right_knee":person_kpts[14],
                    "left_ankle":person_kpts[15],
                    "right_ankle":person_kpts[16]
                }

                print(keypoints)

                # torso_height = distance_between_midpoints([keypoints["left_shoulder"],keypoints["right_shoulder"]],[keypoints["left_hip"],keypoints["right_hip"]])

    # Show the video output
    #cv2.imshow("Person Detection Test Stream",frame)

    # Allow OpenCV to process window events and listen for exit key ('q')
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
