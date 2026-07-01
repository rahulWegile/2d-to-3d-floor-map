import re

with open('rewrite_v6.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the native labeled logic
start_str = "# --- NATIVE LABELED LOGIC (NO V4 CALLS) ---"
end_str = "# --- NATIVE TETRIS POST-PROCESSING ---"
start_idx = content.find(start_str)
end_idx = content.find(end_str)

if start_idx != -1 and end_idx != -1:
    v4_core = content[start_idx:end_idx]
    
    # We need to wrap it in a function
    v4_func = f'''def _expand_rooms_v4(rooms_raw, wall_mask, wall_thickness, height, width):
    import numpy as np
    import cv2
    import os
    from collections import defaultdict, deque
    
    aspect = height / width
    def to_3d(px, py):
        return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)
    def to_px(nx, nz):
        return int((nx + 10) / 20 * width), int((nz / aspect + 10) / 20 * height)
        
    working_free = (wall_mask == 0).astype(np.uint8) * 255
    final_rooms = []
    
    def expand_from_point(cx, cy, current_free):
        x1 = x2 = cx
        y1 = y2 = cy
        fl = fr = ft = fb = False
        while not (fl and fr and ft and fb):
            ox1, oy1, ox2, oy2 = x1, y1, x2, y2
            if not fl:
                if ox1 - 1 >= 0 and current_free[oy1:oy2 + 1, ox1 - 1].all(): x1 = ox1 - 1
                else: fl = True
            if not fr:
                if ox2 + 1 < width and current_free[oy1:oy2 + 1, ox2 + 1].all(): x2 = ox2 + 1
                else: fr = True
            if not ft:
                if oy1 - 1 >= 0 and current_free[oy1 - 1, ox1:ox2 + 1].all(): y1 = oy1 - 1
                else: ft = True
            if not fb:
                if oy2 + 1 < height and current_free[oy2 + 1, ox1:ox2 + 1].all(): y2 = oy2 + 1
                else: fb = True
            if x1 == ox1 and x2 == ox2 and y1 == oy1 and y2 == oy2: break
        if x2 - x1 < 4 or y2 - y1 < 4: return None
        return x1, y1, x2, y2

'''
    
    # Unindent v4_core by 8 spaces
    lines = v4_core.split('\\n')
    for line in lines:
        if line.startswith('        '):
            v4_func += line[4:] + '\\n'
        else:
            v4_func += line + '\\n'
            
    v4_func += '    return final_rooms\\n\\n'
    
    with open(r'C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\app\services\vision\algorithms.py', 'a', encoding='utf-8') as f:
        f.write(v4_func)
    print("V4 successfully reconstructed and appended!")
else:
    print("Could not find native logic blocks in rewrite_v6.py")
