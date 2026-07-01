import cv2
from app.services.vision.pipeline import process_image
img_path = r'c:\Users\Mehak\OneDrive\Desktop\Floor to 3D\image copy 5.png'
with open(img_path, 'rb') as f:
    img_bytes = f.read()
walls, rooms, w, h = process_image(img_bytes)
print(f'Rooms detected in fallback: {len(rooms)}')
