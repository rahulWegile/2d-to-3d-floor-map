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
    v6 pipeline (The Ultimate Architecture - 100% Native):
    \"\"\"
    import numpy as np
    import cv2
    import os
    from collections import defaultdict, deque
    
    os.makedirs("uploads/debug", exist_ok=True)
    
    aspect = height / width
    def to_3d(px, py):
        return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)
    def to_px(nx, nz):
        return int((nx + 10) / 20 * width), int((nz / aspect + 10) / 20 * height)

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

    def expand_tetris(cx, cy, current_free):
        if cy < 0 or cy >= height or cx < 0 or cx >= width or current_free[cy, cx] == 0:
            return None
        rect = expand_from_point(cx, cy, current_free)
        if not rect: return None
        x1, y1, x2, y2 = rect
        if x2 - x1 < 10 or y2 - y1 < 10: return None
        return rect

    final_rooms = []
    working_free = free.copy()
    min_area = int(height * width * 0.003)

    if len(rooms_raw) > 0:
        # --- NATIVE LABELED LOGIC (NO V4 CALLS) ---
        dist = cv2.distanceTransform(working_free, cv2.DIST_L2, 5)
        dist_smooth = cv2.GaussianBlur(dist, (15, 15), 0)
        local_max = cv2.dilate(dist_smooth, np.ones((7,7)))
        cores = ((dist_smooth == local_max) & (dist_smooth > 2)).astype(np.uint8) * 255
        cores = cv2.dilate(cores, np.ones((3,3)))
        num_labels, comp_map = cv2.connectedComponents(cores)

        queue = deque()
        region_map = np.zeros_like(comp_map, dtype=np.int32)
        ys, xs = np.where(comp_map > 0)
        for y, x in zip(ys, xs):
            queue.append((x, y, comp_map[y, x]))
            region_map[y, x] = comp_map[y, x]

        while queue:
            x, y, cid = queue.popleft()
            for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    if working_free[ny, nx] > 0 and region_map[ny, nx] == 0:
                        region_map[ny, nx] = cid
                        queue.append((nx, ny, cid))

        core_to_labels = defaultdict(list)
        for idx, room in enumerate(rooms_raw):
            sx, sy = to_px(room['x'], room['z'])
            cid = region_map[sy, sx]
            if cid == 0:
                found = 0
                for r in range(1, int(min(width, height) * 0.1), 2):
                    y_min = max(0, sy - r); y_max = min(height - 1, sy + r)
                    x_min = max(0, sx - r); x_max = min(width - 1, sx + r)
                    roi = region_map[y_min:y_max+1, x_min:x_max+1]
                    if np.any(roi > 0):
                        ys_roi, xs_roi = np.where(roi > 0)
                        ys_global = ys_roi + y_min; xs_global = xs_roi + x_min
                        dists = (xs_global - sx)**2 + (ys_global - sy)**2
                        min_idx = np.argmin(dists)
                        found = region_map[ys_global[min_idx], xs_global[min_idx]]
                        break
                cid = found
            if cid > 0:
                core_to_labels[cid].append((idx, sx, sy))

        room_masks = {}
        for cid, labels in core_to_labels.items():
            core_mask = (region_map == cid)
            if len(labels) == 1:
                room_masks[labels[0][0]] = core_mask
            else:
                ys, xs = np.where(core_mask)
                pts = np.column_stack((xs, ys))
                label_pts = np.array([[l[1], l[2]] for l in labels])
                dists = np.sum((pts[:, None, :] - label_pts[None, :, :])**2, axis=2)
                closest_idx = np.argmin(dists, axis=1)
                for i, l in enumerate(labels):
                    idx = l[0]
                    sub_mask = np.zeros_like(core_mask, dtype=bool)
                    sub_mask[ys[closest_idx == i], xs[closest_idx == i]] = True
                    room_masks[idx] = sub_mask

        sorted_rooms = sorted(enumerate(rooms_raw), key=lambda x: x[1]['name'].lower())
        base_rooms_extracted = []
        
        for idx, room in sorted_rooms:
            sx, sy = to_px(room['x'], room['z'])
            if idx not in room_masks: continue
            mask = room_masks[idx]
            if not np.any(mask): continue
            
            if mask[sy, sx] and working_free[sy, sx] != 0:
                cx, cy = sx, sy
            else:
                M = cv2.moments(mask.astype(np.uint8))
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                else:
                    cx, cy = sx, sy
                if not mask[cy, cx]:
                    ys, xs = np.where(mask)
                    dists = (xs - cx)**2 + (ys - cy)**2
                    min_idx = np.argmin(dists)
                    cx, cy = xs[min_idx], ys[min_idx]

            rect = expand_from_point(cx, cy, working_free)
            if rect:
                x1, y1, x2, y2 = rect
                working_free[y1:y2+1, x1:x2+1] = 0
                x1 += 3; x2 -= 3; y1 += 3; y2 -= 3
                if x2 - x1 >= 4 and y2 - y1 >= 4:
                    rx1, rz1 = to_3d(x1, y1)
                    rx2, rz2 = to_3d(x2, y2)
                    room_data = {
                        "name": room['name'],
                        "x": room['x'], "z": room['z'],
                        "w": abs(rx2 - rx1), "h": abs(rz2 - rz1),
                        "polygon": [{"x": rx1, "z": rz1}, {"x": rx2, "z": rz1}, {"x": rx2, "z": rz2}, {"x": rx1, "z": rz2}],
                        "px1": x1, "py1": y1, "px2": x2, "py2": y2
                    }
                    base_rooms_extracted.append(room_data)
                    final_rooms.append({k:v for k,v in room_data.items() if k not in ["px1", "py1", "px2", "py2"]})

        # --- NATIVE TETRIS POST-PROCESSING ---
        for r in base_rooms_extracted:
            px1, py1, px2, py2 = r["px1"], r["py1"], r["px2"], r["py2"]
            faces = [
                ((px1 + px2)//2, py1 - 5), # Top
                ((px1 + px2)//2, py2 + 5), # Bottom
                (px1 - 5, (py1 + py2)//2), # Left
                (px2 + 5, (py1 + py2)//2)  # Right
            ]
            for fx, fy in faces:
                rect = expand_tetris(fx, fy, working_free)
                if rect:
                    nx1, ny1, nx2, ny2 = rect
                    area = (nx2 - nx1) * (ny2 - ny1)
                    if area > min_area:
                        working_free[ny1:ny2+1, nx1:nx2+1] = 0
                        nx1 += 2; nx2 -= 2; ny1 += 2; ny2 -= 2
                        rx1, rz1 = to_3d(nx1, ny1)
                        rx2, rz2 = to_3d(nx2, ny2)
                        final_rooms.append({
                            "name": r["name"],
                            "polygon": [{"x": rx1, "z": rz1}, {"x": rx2, "z": rz1}, {"x": rx2, "z": rz2}, {"x": rx1, "z": rz2}],
                            "x": (rx1 + rx2)/2, "z": (rz1 + rz2)/2,
                            "w": abs(rx2 - rx1), "h": abs(rz2 - rz1)
                        })

    else:
        # --- NATIVE UNLABELED FALLBACK ---
        dist = cv2.distanceTransform(working_free, cv2.DIST_L2, 5)
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
            score = dist_region[cy, cx]
            candidates.append({'cx': cx, 'cy': cy, 'score': score})
            
        candidates.sort(key=lambda c: c['score'], reverse=True)

        for i, cand in enumerate(candidates):
            cx, cy = cand['cx'], cand['cy']
            if working_free[cy, cx] == 0: continue
            rect = expand_from_point(cx, cy, working_free)
            if rect:
                x1, y1, x2, y2 = rect
                if (x2 - x1) * (y2 - y1) >= min_area:
                    working_free[y1:y2+1, x1:x2+1] = 0
                    x1 += 3; x2 -= 3; y1 += 3; y2 -= 3
                    rx1, rz1 = to_3d(x1, y1)
                    rx2, rz2 = to_3d(x2, y2)
                    final_rooms.append({
                        "name": f"Room {i + 1}",
                        "x": (rx1 + rx2)/2, "z": (rz1 + rz2)/2,
                        "w": abs(rx2 - rx1), "h": abs(rz2 - rz1),
                        "polygon": [{"x": rx1, "z": rz1}, {"x": rx2, "z": rz1}, {"x": rx2, "z": rz2}, {"x": rx1, "z": rz2}]
                    })

    return final_rooms
'''

new_lines = lines[:start_idx] + [v6_code, '\n'] + lines[end_idx:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("V6 replaced successfully.")
