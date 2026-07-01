import cv2
from app.services.vision.pipeline import process_image
img_path = r'c:\Users\Mehak\OneDrive\Desktop\Floor to 3D\image copy 5.png'
with open(img_path, 'rb') as f:
    img_bytes = f.read()
walls, rooms, w, h = process_image(img_bytes)
for i, r in enumerate(rooms):
    print(f'Room {i}: {r.get("w"):.2f} x {r.get("h"):.2f}')
