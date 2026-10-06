import cv2
from ultralytics import YOLO

model = YOLO("models/yolov8n.pt")

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: Failed to open camera")
    exit()

print("Camera stream started. Press 'Q' to quit.")

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
        boxes = result.boxes

        for box in boxes:
            # Convert bounding box to ints
            x1,y1,x2,y2 = box.xyxy[0].cpu().numpy().astype(int)

            # Extract confidence
            conf = float(box.conf[0].cpu().numpy())

            # Calculate center coords
            center_x = int((x1+x2)/2)
            center_y = int((y1+y2)/2)

            # Draw bounding box
            cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)

            # Draw dot at center
            cv2.circle(frame,(center_x,center_y),5,(0,0,255),-1)

            # Draw label
            cv2.putText(frame,f"Person {conf:.2f}",(x1,y1-10),cv2.FONT_HERSHEY_SIMPLEX,1,(0,255,0),2)

    # Show the video output
    cv2.imshow("Person Detection Test Stream",frame)

    # Allow OpenCV to process window events and listen for exit key ('q')
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
