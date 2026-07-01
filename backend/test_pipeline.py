from app.services.vision.pipeline import process_image
import os
import json

with open(r"C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\image copy 4.png", "rb") as f:
    img_bytes = f.read()
    
res = process_image(img_bytes)
print(json.dumps(res, indent=2))
