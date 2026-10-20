import cv2
from ultralytics import YOLO

model = YOLO("models/yolov8n.pt")
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: Failed to open camera")
    exit()

print("Camera stream started. Press 'Q' to quit.")


def draw_bbox(frame,box_dict,label,color=(0,0,255)):
    # Get coords and confidence
    x1,y1,x2,y2 = box_dict["coords"]

    # Draw bounding box
    cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)

    # Draw label
    cv2.putText(frame,label,(x1,y1-10),cv2.FONT_HERSHEY_SIMPLEX,1,color,2)


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

            if conf > confident_bbox["conf"]:
                confident_bbox = {
                    "id":box_count,
                    "coords":(x1,y1,x2,y2),
                    "area":area,
                    "conf":conf,
                    "object":box
                }

            box_count += 1

        # Check if the largest and most confident are the same (this is the goal)
        if largest_bbox["id"] == confident_bbox["id"] and largest_bbox["id"] != -1:
            draw_bbox(frame,largest_bbox,f"Ideal target",color=(0,255,0))
        else: # otherwise, draw 2 boxes
            # Draw bounding box around largest box (if it exists)
            if largest_bbox["id"] != -1:
                draw_bbox(frame,largest_bbox,f"Largest area: {largest_bbox["area"]} (id={largest_bbox["id"]})")

            # Draw bounding box around most confident box (if it exists)
            if confident_bbox["id"] != -1:
                draw_bbox(frame,confident_bbox,f"Most conf: {confident_bbox["conf"]:.2f} (id={confident_bbox["id"]})")

    # Show the video output
    cv2.imshow("Person Detection Test Stream",frame)

    # Allow OpenCV to process window events and listen for exit key ('q')
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
