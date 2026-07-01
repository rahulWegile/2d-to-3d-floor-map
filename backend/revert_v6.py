import sys

file_path = r'C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\app\services\vision\algorithms.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if line.startswith('def _expand_rooms_v6'):
        start_idx = i
    if line.startswith('def _expand_rooms_v4'):
        end_idx = i
        break
        
if start_idx == -1 or end_idx == -1:
    print('Failed to find indices')
    sys.exit(1)

v6_code = '''def _expand_rooms_v6(rooms_raw, wall_mask, wall_thickness, height, width):
    \"\"\"
    v6 pipeline (The Ultimate Architecture):
    - Exact copy of v5, ready for new refinements.
    \"\"\"
    import numpy as np
    import cv2
    import os

    if len(rooms_raw) > 0:
        return _expand_rooms_v4(rooms_raw, wall_mask, wall_thickness, height, width)

    os.makedirs("uploads/debug", exist_ok=True)
    
    # ── V6 PRISTINE WALL EXTRACTION (Thickness Profiling) ────────────────
    dist_walls = cv2.distanceTransform(wall_mask, cv2.DIST_L2, 5)
    core_mask = (dist_walls > wall_thickness * 0.25).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    pristine_walls = cv2.morphologyEx(core_mask, cv2.MORPH_CLOSE, kernel)
    cv2.imwrite("uploads/debug/v6_pristine_walls.png", pristine_walls)
    wall_mask = pristine_walls
    cv2.imwrite("uploads/debug/v6_walls.png", wall_mask)
    # ──────────────────────────────────────────────────────────

    cv2.imwrite("uploads/debug/v6_walls_fallback.png", wall_mask)

    # 1. Solid building footprint to prevent outside detections
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(50, wall_thickness * 5), max(50, wall_thickness * 5)))
    closed_walls = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, close_kernel)
    
    contours, _ = cv2.findContours(closed_walls, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    building_mask = np.zeros_like(wall_mask)
    if contours:
        largest_contour = max(contours, key=cv2.contourArea)
        cv2.drawContours(building_mask, [largest_contour], -1, 255, -1)
    else:
        building_mask.fill(255)
        
    cv2.imwrite("uploads/debug/v6_building_mask.png", building_mask)

    # 2. Free space restricted to inside the building
    free = (wall_mask == 0).astype(np.uint8) * 255
    free = cv2.bitwise_and(free, building_mask)
    
    # 3. Robust Room Detection using Distance Transform (prevents missing small rooms)
    dist = cv2.distanceTransform(free, cv2.DIST_L2, 5)
    dist_smooth = cv2.GaussianBlur(dist, (15, 15), 0)
    
    local_max = cv2.dilate(dist_smooth, np.ones((7,7)))
    core_threshold = 2
    cores = ((dist_smooth == local_max) & (dist_smooth > core_threshold)).astype(np.uint8) * 255
    cores = cv2.dilate(cores, np.ones((3,3)))
    
    num_labels, comp_map = cv2.connectedComponents(cores)
    
    # Extract candidates from cores
    candidates = []
    for cid in range(1, num_labels):
        region_mask = (comp_map == cid)
        if region_mask.sum() == 0: continue
            
        dist_region = dist_smooth.copy()
        dist_region[~region_mask] = 0
        peak = np.unravel_index(np.argmax(dist_region), dist_region.shape)
        cy, cx = int(peak[0]), int(peak[1])
        score = dist_region[cy, cx]
        candidates.append({'cx': cx, 'cy': cy, 'score': score})
        
    # Sort from largest/deepest room to smallest
    candidates.sort(key=lambda c: c['score'], reverse=True)

    # Helper: 4-way expansion
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

    # 4. Expand rooms and prevent duplicates
    working_free = free.copy()
    valid_rooms = []
    debug_rooms = cv2.cvtColor(free, cv2.COLOR_GRAY2BGR)

    for cand in candidates:
        cx, cy = cand['cx'], cand['cy']
        
        if working_free[cy, cx] == 0:
            continue
            
        rect = expand_from_point(cx, cy, working_free)
        if rect:
            x1, y1, x2, y2 = rect
            area = (x2 - x1) * (y2 - y1)
            
            if area >= max(50, int(height * width * 0.0005)):
                working_free[y1:y2+1, x1:x2+1] = 0
                x1 += 3; x2 -= 3; y1 += 3; y2 -= 3
                if x2 > x1 and y2 > y1:
                    valid_rooms.append({'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})
                    cv2.rectangle(debug_rooms, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
    cv2.imwrite("uploads/debug/v6_final_rooms.png", debug_rooms)

    # 5. Construct final output
    aspect = height / width
    def to_3d(px, py):
        return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)

    final_rooms = []
    for i, vr in enumerate(valid_rooms):
        x1, y1, x2, y2 = vr['x1'], vr['y1'], vr['x2'], vr['y2']
        
        orig_x, orig_z = to_3d((x1+x2)/2, (y1+y2)/2)
        rx1, rz1 = to_3d(x1, y1)
        rx2, rz2 = to_3d(x2, y2)
        
        final_rooms.append({
            "name": f"Room {i + 1}",
            "x": orig_x, "z": orig_z,
            "w": abs(rx2 - rx1), "h": abs(rz2 - rz1),
            "polygon": [
                {"x": rx1, "z": rz1}, {"x": rx2, "z": rz1},
                {"x": rx2, "z": rz2}, {"x": rx1, "z": rz2},
            ]
        })
        
    return final_rooms
'''

new_lines = lines[:start_idx] + [v6_code, '\n'] + lines[end_idx:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Reverted to base V6 successfully.")
