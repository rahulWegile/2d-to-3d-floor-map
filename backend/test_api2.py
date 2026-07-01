import cv2
import json
from app.services.vision.pipeline import process_image
img_path = r'c:\Users\Mehak\OneDrive\Desktop\Floor to 3D\image copy 5.png'
with open(img_path, 'rb') as f:
    img_bytes = f.read()
walls, rooms, w, h = process_image(img_bytes)
print(json.dumps(rooms[0:2], indent=2))
