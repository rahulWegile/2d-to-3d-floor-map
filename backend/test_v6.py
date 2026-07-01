import numpy as np
import cv2
import sys
from app.services.vision.algorithms import _expand_rooms_v6

try:
    rooms_raw = [{'name': 'Room 1', 'x': 0, 'z': 0}]
    wall_mask = np.zeros((500, 500), dtype=np.uint8)
    # create a box
    cv2.rectangle(wall_mask, (50, 50), (450, 450), 255, 2)
    # fill room center with some free space
    
    result = _expand_rooms_v6(rooms_raw, wall_mask, 5, 500, 500)
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
