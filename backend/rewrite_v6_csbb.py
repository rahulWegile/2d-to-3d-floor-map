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
    v6 pipeline: Focuses EXCLUSIVELY on fixing unlabeled blueprints using CSBB (Corner-Subtracted Bounding Box).
    Safeguards labeled blueprints by routing them to V4.
    \"\"\"
    import numpy as np
    import cv2
    import os
    
    os.makedirs("uploads/debug", exist_ok=True)
    
    # --- ABSOLUTE SAFEGUARD: DO NOT AFFECT LABELED WORKING ---
    if len(rooms_raw) > 0:
        return _expand_rooms_v4(rooms_raw, wall_mask, wall_thickness, height, width)
        
    # --- CSBB LOGIC FOR UNLABELED BLUEPRINTS ONLY ---
    aspect = height / width
    def to_3d(px, py):
        return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)

    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(50, wall_thickness * 5), max(50, wall_thickness * 5)))
    closed_walls = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, close_kernel)
    
    contours, _ = cv2.findContours(closed_walls, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    building_mask = np.zeros_like(wall_mask)
    if contours:
        largest_contour = max(contours, key=cv2.contourArea)
        cv2.drawContours(building_mask, [largest_contour], -1, 255, -1)
    else:
        building_mask.fill(255)

    free = (wall_mask == 0).astype(np.uint8) * 255
    free = cv2.bitwise_and(free, building_mask)

    dist = cv2.distanceTransform(free, cv2.DIST_L2, 5)
    dist_smooth = cv2.GaussianBlur(dist, (45, 45), 0)
    local_max = cv2.dilate(dist_smooth, np.ones((15, 15)))
    cores = ((dist_smooth == local_max) & (dist_smooth > 5)).astype(np.uint8) * 255
    cores = cv2.dilate(cores, np.ones((5, 5)))
    
    num_labels, comp_map = cv2.connectedComponents(cores)
    
    candidates = []
    for cid in range(1, num_labels):
        region_mask = (comp_map == cid)
        if region_mask.sum() == 0: continue
        dist_region = dist_smooth.copy()
        dist_region[~region_mask] = 0
        peak = np.unravel_index(np.argmax(dist_region), dist_region.shape)
        cy, cx = int(peak[0]), int(peak[1])
        candidates.append({'cx': cx, 'cy': cy, 'score': dist_region[cy, cx]})
        
    candidates.sort(key=lambda c: c['score'], reverse=True)

    working_free = free.copy()
    final_rooms = []
    min_area = int(height * width * 0.003)

    # CSBB Implementation
    for i, cand in enumerate(candidates):
        cx, cy = cand['cx'], cand['cy']
        if working_free[cy, cx] == 0: continue
        
        # 1. Flood fill from center to find true room blob
        mask = np.zeros((height + 2, width + 2), np.uint8)
        cv2.floodFill(working_free.copy(), mask, (cx, cy), 255, 0, 0, 4 | (255 << 8))
        room_blob = mask[1:height+1, 1:width+1]
        
        # 2. Find bounding box of the blob
        ys, xs = np.where(room_blob == 255)
        if len(ys) < 100:
            working_free[cy, cx] = 0
            continue
            
        x_min, x_max = xs.min(), xs.max()
        y_min, y_max = ys.min(), ys.max()
        
        if (x_max - x_min) * (y_max - y_min) < min_area:
            working_free[y_min:y_max+1, x_min:x_max+1] = 0
            continue

        # 3. Analyze the 4 corners of the Bounding Box
        corner_w = (x_max - x_min) // 3
        corner_h = (y_max - y_min) // 3
        
        corners = {
            "TL": (x_min, y_min, x_min + corner_w, y_min + corner_h),
            "TR": (x_max - corner_w, y_min, x_max, y_min + corner_h),
            "BL": (x_min, y_max - corner_h, x_min + corner_w, y_max),
            "BR": (x_max - corner_w, y_max - corner_h, x_max, y_max)
        }
        
        # Determine which corners are mostly empty (not in the blob)
        cutouts = []
        for name, (cx1, cy1, cx2, cy2) in corners.items():
            roi = room_blob[cy1:cy2, cx1:cx2]
            if np.sum(roi == 255) < (corner_w * corner_h * 0.2): # If less than 20% filled, it's an empty corner
                cutouts.append(name)

        # 4. Construct orthogonal polygon by subtracting corners
        # Base rectangle points (Clockwise: TL -> TR -> BR -> BL)
        # Note: We must ensure counter-clockwise for 3D? Three.js deals with it using DoubleSide.
        
        pts = []
        if "TL" in cutouts:
            pts.extend([
                {"x": x_min + corner_w, "z": y_min},
                {"x": x_max, "z": y_min},
                {"x": x_max, "z": y_max},
                {"x": x_min, "z": y_max},
                {"x": x_min, "z": y_min + corner_h},
                {"x": x_min + corner_w, "z": y_min + corner_h}
            ])
        elif "TR" in cutouts:
            pts.extend([
                {"x": x_min, "z": y_min},
                {"x": x_max - corner_w, "z": y_min},
                {"x": x_max - corner_w, "z": y_min + corner_h},
                {"x": x_max, "z": y_min + corner_h},
                {"x": x_max, "z": y_max},
                {"x": x_min, "z": y_max}
            ])
        elif "BL" in cutouts:
            pts.extend([
                {"x": x_min, "z": y_min},
                {"x": x_max, "z": y_min},
                {"x": x_max, "z": y_max},
                {"x": x_min + corner_w, "z": y_max},
                {"x": x_min + corner_w, "z": y_max - corner_h},
                {"x": x_min, "z": y_max - corner_h}
            ])
        elif "BR" in cutouts:
            pts.extend([
                {"x": x_min, "z": y_min},
                {"x": x_max, "z": y_min},
                {"x": x_max, "z": y_max - corner_h},
                {"x": x_max - corner_w, "z": y_max - corner_h},
                {"x": x_max - corner_w, "z": y_max},
                {"x": x_min, "z": y_max}
            ])
        else:
            # Standard Rectangle
            pts.extend([
                {"x": x_min, "z": y_min},
                {"x": x_max, "z": y_min},
                {"x": x_max, "z": y_max},
                {"x": x_min, "z": y_max}
            ])

        # Shave 3 pixels off to avoid wall overlap
        working_free[y_min:y_max+1, x_min:x_max+1] = 0

        # Convert to 3D and output
        polygon_3d = []
        for p in pts:
            rx, rz = to_3d(p["x"], p["z"])
            polygon_3d.append({"x": rx, "z": rz})

        c_x, c_z = to_3d((x_min + x_max)/2, (y_min + y_max)/2)
        rx1, rz1 = to_3d(x_min, y_min)
        rx2, rz2 = to_3d(x_max, y_max)
        
        final_rooms.append({
            "name": f"Room {i + 1}",
            "x": c_x, "z": c_z,
            "w": abs(rx2 - rx1), "h": abs(rz2 - rz1),
            "polygon": polygon_3d
        })

    return final_rooms
'''

new_lines = lines[:start_idx] + [v6_code, '\n'] + lines[end_idx:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("V6 replaced with CSBB successfully.")
