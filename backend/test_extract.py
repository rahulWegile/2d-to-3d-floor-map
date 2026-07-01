from app.services.vision.core import _extract_rooms
import cv2
import json
import sys

img = cv2.imread(r"C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\image copy 4.png")
if img is None:
    print("Could not load image")
    sys.exit(1)
height, width = img.shape[:2]
rooms_raw = _extract_rooms(img, height, width)

print(json.dumps(rooms_raw, indent=2))
