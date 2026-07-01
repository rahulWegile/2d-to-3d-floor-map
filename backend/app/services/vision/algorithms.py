import cv2
import os

def _expand_rooms_v6(rooms_raw, wall_mask, wall_thickness, height, width):
    """
    v5 pipeline (The Ultimate Architecture):
    - If OCR labels exist, preserves V4 behavior perfectly.
    - If no OCR labels exist, uses a hybrid geometry fallback:
      1. Building mask to strictly prevent outside rooms.
      2. Distance transform cores to find ALL rooms (prevents missing small rooms/hallways).
      3. Expands from deepest cores first, marking space as occupied to prevent duplicate tiles.
    """
    import numpy as np
    import cv2
    import os

    if len(rooms_raw) > 0:
        return _expand_rooms_v4(rooms_raw, wall_mask, wall_thickness, height, width)

    os.makedirs("uploads/debug", exist_ok=True)
    cv2.imwrite("uploads/debug/v5_walls.png", wall_mask)

    aspect = height / width

    def to_3d(px, py):
        return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)

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

    cv2.imwrite("uploads/debug/v5_building_mask.png", building_mask)

    # 2. Free space restricted to inside the building
    free = (wall_mask == 0).astype(np.uint8) * 255
    free = cv2.bitwise_and(free, building_mask)
    annot_k = max(3, min(int(round(wall_thickness * 0.35)), 9))
    if annot_k % 2 == 0: annot_k += 1
    small_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    large_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (annot_k, annot_k))
    free = cv2.morphologyEx(free, cv2.MORPH_CLOSE, small_kernel)
    free = cv2.morphologyEx(free, cv2.MORPH_CLOSE, large_kernel)
    free = cv2.morphologyEx(free, cv2.MORPH_OPEN, small_kernel)

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

        # If this core is inside an area already occupied by a previous expansion,
        # it's a noisy secondary core in the same room! Skip it to prevent duplicate tiles.
        if working_free[cy, cx] == 0:
            continue

        rect = expand_from_point(cx, cy, working_free)
        if rect:
            x1, y1, x2, y2 = rect
            area = (x2 - x1) * (y2 - y1)

            # Minimum area check just to filter out severe noise
            if area >= max(50, int(height * width * 0.0005)):
                # Mark as occupied so no other cores can spawn a room here
                working_free[y1:y2+1, x1:x2+1] = 0

                # Shave off edges for visuals
                x1 += 3; x2 -= 3; y1 += 3; y2 -= 3
                if x2 > x1 and y2 > y1:
                    valid_rooms.append({'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})
                    cv2.rectangle(debug_rooms, (x1, y1), (x2, y2), (0, 255, 0), 2)

    cv2.imwrite("uploads/debug/v5_final_rooms.png", debug_rooms)

    # 5. Construct final output
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

    import json
    with open("uploads/debug/final_rooms_debug.json", "w") as f:
        json.dump(final_rooms, f, indent=2)
    return final_rooms


def _expand_rooms_v5(rooms_raw, wall_mask, wall_thickness, height, width):
    """
    v5 pipeline (The Ultimate Architecture):
    - If OCR labels exist, preserves V4 behavior perfectly.
    - If no OCR labels exist, uses a hybrid geometry fallback:
      1. Building mask to strictly prevent outside rooms.
      2. Distance transform cores to find ALL rooms (prevents missing small rooms/hallways).
      3. Expands from deepest cores first, marking space as occupied to prevent duplicate tiles.
    """
    import numpy as np
    import cv2
    import os



    if len(rooms_raw) > 0:
        return _expand_rooms_v4(rooms_raw, wall_mask, wall_thickness, height, width)

    os.makedirs("uploads/debug", exist_ok=True)
    cv2.imwrite("uploads/debug/v5_walls.png", wall_mask)

    aspect = height / width

    def to_3d(px, py):
        return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)

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

    cv2.imwrite("uploads/debug/v5_building_mask.png", building_mask)

    # 2. Free space restricted to inside the building
    free = (wall_mask == 0).astype(np.uint8) * 255
    free = cv2.bitwise_and(free, building_mask)
    annot_k = max(3, min(int(round(wall_thickness * 0.35)), 9))
    if annot_k % 2 == 0: annot_k += 1
    small_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    large_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (annot_k, annot_k))
    free = cv2.morphologyEx(free, cv2.MORPH_CLOSE, small_kernel)
    free = cv2.morphologyEx(free, cv2.MORPH_CLOSE, large_kernel)
    free = cv2.morphologyEx(free, cv2.MORPH_OPEN, small_kernel)

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

        # If this core is inside an area already occupied by a previous expansion,
        # it's a noisy secondary core in the same room! Skip it to prevent duplicate tiles.
        if working_free[cy, cx] == 0:
            continue

        rect = expand_from_point(cx, cy, working_free)
        if rect:
            x1, y1, x2, y2 = rect
            area = (x2 - x1) * (y2 - y1)

            # Minimum area check just to filter out severe noise
            if area >= max(50, int(height * width * 0.0005)):
                # Mark as occupied so no other cores can spawn a room here
                working_free[y1:y2+1, x1:x2+1] = 0

                # Shave off edges for visuals
                x1 += 3; x2 -= 3; y1 += 3; y2 -= 3
                if x2 > x1 and y2 > y1:
                    valid_rooms.append({'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})
                    cv2.rectangle(debug_rooms, (x1, y1), (x2, y2), (0, 255, 0), 2)

    cv2.imwrite("uploads/debug/v5_final_rooms.png", debug_rooms)

    # 5. Construct final output
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

    import json
    with open("uploads/debug/final_rooms_debug.json", "w") as f:
        json.dump(final_rooms, f, indent=2)
    return final_rooms


def _expand_rooms_v7(rooms_raw, wall_mask, wall_thickness, height, width):
    """
    v7 pipeline:
    - Uses v6 OpenCV logic (fallback) when API fails.
    """
    import numpy as np
    import cv2
    import os

    os.makedirs("uploads/debug", exist_ok=True)
    cv2.imwrite("uploads/debug/v7_walls.png", wall_mask)

    aspect = height / width

    def to_3d(px, py):
        return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)

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

    cv2.imwrite("uploads/debug/v7_building_mask.png", building_mask)

    wall_mask = wall_mask.copy()
    wall_mask[building_mask == 0] = 255

    if len(rooms_raw) > 0:
        return _expand_rooms_labeled(rooms_raw, wall_mask, wall_thickness, height, width)

    # 2. Free space restricted to inside the building
    free = (wall_mask == 0).astype(np.uint8) * 255
    free = cv2.bitwise_and(free, building_mask)
    annot_k = max(3, min(int(round(wall_thickness * 0.35)), 9))
    if annot_k % 2 == 0: annot_k += 1
    small_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    large_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (annot_k, annot_k))
    free = cv2.morphologyEx(free, cv2.MORPH_CLOSE, small_kernel)
    free = cv2.morphologyEx(free, cv2.MORPH_CLOSE, large_kernel)
    free = cv2.morphologyEx(free, cv2.MORPH_OPEN, small_kernel)

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

        # If this core is inside an area already occupied by a previous expansion,
        # it's a noisy secondary core in the same room! Skip it to prevent duplicate tiles.
        if working_free[cy, cx] == 0:
            continue

        rect = expand_from_point(cx, cy, working_free)
        if rect:
            x1, y1, x2, y2 = rect
            area = (x2 - x1) * (y2 - y1)

            # Minimum area check just to filter out severe noise
            if area >= max(50, int(height * width * 0.0005)):
                # Mark as occupied so no other cores can spawn a room here
                working_free[y1:y2+1, x1:x2+1] = 0

                # Shave off edges for visuals
                x1 += 3; x2 -= 3; y1 += 3; y2 -= 3
                if x2 > x1 and y2 > y1:
                    valid_rooms.append({'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})
                    cv2.rectangle(debug_rooms, (x1, y1), (x2, y2), (0, 255, 0), 2)

    cv2.imwrite("uploads/debug/v7_final_rooms.png", debug_rooms)

    # 5. Construct final output
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

    import json
    with open("uploads/debug/final_rooms_debug.json", "w") as f:
        json.dump(final_rooms, f, indent=2)
    return final_rooms


def _expand_rooms_v4(rooms_raw, wall_mask, wall_thickness, height, width):
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
    annot_k = max(3, min(int(round(wall_thickness * 0.35)), 9))
    if annot_k % 2 == 0: annot_k += 1
    small_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    large_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (annot_k, annot_k))
    working_free = cv2.morphologyEx(working_free, cv2.MORPH_CLOSE, small_kernel)
    working_free = cv2.morphologyEx(working_free, cv2.MORPH_CLOSE, large_kernel)
    working_free = cv2.morphologyEx(working_free, cv2.MORPH_OPEN, small_kernel)
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
        if "box_2d" in room:
            xmin, xmax, ymin, ymax = room["box_2d"]
            # Convert 0-1000 scale to pixel bounds, ensuring we stay within image
            px_min = max(0, int(xmin / 1000.0 * width))
            px_max = min(width - 1, int(xmax / 1000.0 * width))
            py_min = max(0, int(ymin / 1000.0 * height))
            py_max = min(height - 1, int(ymax / 1000.0 * height))
            
            if px_max > px_min and py_max > py_min:
                roi = dist_smooth[py_min:py_max, px_min:px_max]
                if np.any(roi > 0):
                    peak = np.unravel_index(np.argmax(roi), roi.shape)
                    sx = px_min + peak[1]
                    sy = py_min + peak[0]
                else:
                    sx, sy = to_px(room['x'], room['z'])
            else:
                sx, sy = to_px(room['x'], room['z'])
        else:
            sx, sy = to_px(room['x'], room['z'])
            
        # Clamp coordinates to ensure they are strictly inside the image bounds
        sx = max(0, min(width - 1, sx))
        sy = max(0, min(height - 1, sy))
        
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
            
            # 1. Erase the ORIGINAL rectangle from working_free so we don't spawn overlapping tiles!
            working_free[y1:y2+1, x1:x2+1] = 0
            
            # 2. Add spacing over wall so tiles don't touch the walls
            spacing = max(4, int(wall_thickness * 0.4))
            x1 += spacing
            y1 += spacing
            x2 -= spacing
            y2 -= spacing
            
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


    return final_rooms


def expand_from_point_in_mask(cx, cy, room_mask_u8, height, width):
    """
    4-way rectangle expansion from (cx, cy) bounded to room_mask_u8.

    Unlike the expand_from_point closure in v5-v7 which operates on a shared
    global working_free mask (and erases it after each room), this function
    works on a per-room mask that is never modified.  Rooms are physically
    separated by their individual masks so no tile can leak into a wall or
    an adjacent room's space.

    room_mask_u8: uint8 array (H, W), 255 where this room may expand.
                  Must be the intersection of the watershed segment with
                  the original free-space mask — wall pixels are 0.
    Returns (x1, y1, x2, y2) bounding box, or None if result is too small.
    """
    x1 = x2 = cx
    y1 = y2 = cy
    fl = fr = ft = fb = False
    while not (fl and fr and ft and fb):
        ox1, oy1, ox2, oy2 = x1, y1, x2, y2
        if not fl:
            if ox1 - 1 >= 0 and room_mask_u8[oy1:oy2 + 1, ox1 - 1].all():
                x1 = ox1 - 1
            else:
                fl = True
        if not fr:
            if ox2 + 1 < width and room_mask_u8[oy1:oy2 + 1, ox2 + 1].all():
                x2 = ox2 + 1
            else:
                fr = True
        if not ft:
            if oy1 - 1 >= 0 and room_mask_u8[oy1 - 1, ox1:ox2 + 1].all():
                y1 = oy1 - 1
            else:
                ft = True
        if not fb:
            if oy2 + 1 < height and room_mask_u8[oy2 + 1, ox1:ox2 + 1].all():
                y2 = oy2 + 1
            else:
                fb = True
        if x1 == ox1 and x2 == ox2 and y1 == oy1 and y2 == oy2:
            break
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    return x1, y1, x2, y2


def _largest_inscribed_rect(mask_u8):
    """
    Return the largest axis-aligned rectangle that fits entirely within mask_u8.

    Uses the O(H*W) histogram + monotonic-stack algorithm:
      • For each row, maintain a histogram of consecutive free rows above each
        column.  Running the classic "max rectangle in histogram" pass over each
        row finds every maximal candidate in a single sweep.
      • This is globally optimal — it never gets trapped in a local maximum the
        way a seed-based greedy expansion does.

    mask_u8 : uint8 numpy array (H, W) — non-zero pixels are passable.
    Returns  : (x1, y1, x2, y2) inclusive pixel coordinates, or None.
    """
    import numpy as np

    H, W = mask_u8.shape
    free = mask_u8 > 0
    heights = np.zeros(W, dtype=np.int32)
    best_area = 0
    best = None

    for row in range(H):
        # Vectorised height update: reset to 0 on wall pixels, else +1.
        heights = np.where(free[row], heights + 1, 0)

        # Max rectangle in this histogram — monotonic stack, O(W).
        # Each stack entry is (left_extent_of_bar, bar_height).
        stack = []
        h = heights.tolist()   # list access is faster inside tight Python loop

        for col in range(W + 1):
            bar = h[col] if col < W else 0
            left = col
            while stack and stack[-1][1] > bar:
                sl, sh = stack.pop()
                area = sh * (col - sl)
                if area > best_area:
                    best_area = area
                    # Inclusive bounding box of this maximal rectangle.
                    best = (sl, row - sh + 1, col - 1, row)
                left = sl            # current bar extends leftward to sl
            stack.append((left, bar))

    return best


def _lir_cropped(mask_u8):
    """
    Crop mask_u8 to its non-zero bounding box, run LIR inside that crop,
    and return full-image pixel coordinates (or None).

    Running LIR on the full H×W image when only a small room-sized region is
    non-zero wastes O(H×W) work.  Cropping first reduces each call to
    O(room_h × room_w) — 10-50× faster for typical floor plans.
    Coordinates are translated back to the original image frame before return.
    """
    import numpy as np
    rows_hit = np.any(mask_u8 > 0, axis=1)
    cols_hit = np.any(mask_u8 > 0, axis=0)
    if not np.any(rows_hit) or not np.any(cols_hit):
        return None
    r0 = int(np.argmax(rows_hit))
    r1 = int(len(rows_hit) - 1 - np.argmax(rows_hit[::-1]))
    c0 = int(np.argmax(cols_hit))
    c1 = int(len(cols_hit) - 1 - np.argmax(cols_hit[::-1]))
    local = _largest_inscribed_rect(mask_u8[r0:r1 + 1, c0:c1 + 1])
    if local is None:
        return None
    lx1, ly1, lx2, ly2 = local
    return lx1 + c0, ly1 + r0, lx2 + c0, ly2 + r0


def _expand_rooms_labeled(rooms_raw, wall_mask, wall_thickness, height, width):
    """
    Labeled-room tile placement: v4 region-finding + LIR tile placement.

    Keeps v4's proven distance-transform peak → BFS region-map → label
    assignment pipeline (the part that worked correctly) and replaces ONLY
    the broken final step: greedy expand_from_point with shared working_free
    erasure is swapped for per-region _lir_cropped.

    Result: every room's tile is globally optimal and no room can starve
    another because there is no shared working_free to erase.

    Falls back to _expand_rooms_v4 if LIR produces zero rooms.
    Output format is identical to v4 (name, x, z, w, h, polygon).
    """
    import numpy as np
    import cv2
    from collections import defaultdict, deque

    aspect = height / width

    def to_3d(px, py):
        return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)

    def to_px(nx, nz):
        return int((nx + 10) / 20 * width), int((nz / aspect + 10) / 20 * height)

    # ── Free space (identical to v4) ─────────────────────────────────────────
    working_free = (wall_mask == 0).astype(np.uint8) * 255
    annot_k = max(3, min(int(round(wall_thickness * 0.35)), 9))
    if annot_k % 2 == 0:
        annot_k += 1
    sk3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    ska = cv2.getStructuringElement(cv2.MORPH_RECT, (annot_k, annot_k))
    working_free = cv2.morphologyEx(working_free, cv2.MORPH_CLOSE, sk3)
    working_free = cv2.morphologyEx(working_free, cv2.MORPH_CLOSE, ska)
    working_free = cv2.morphologyEx(working_free, cv2.MORPH_OPEN, sk3)

    # ── Distance transform → peaks → BFS region map (identical to v4) ────────
    dist       = cv2.distanceTransform(working_free, cv2.DIST_L2, 5)
    dist_smooth = cv2.GaussianBlur(dist, (15, 15), 0)
    local_max  = cv2.dilate(dist_smooth, np.ones((7, 7)))
    cores      = ((dist_smooth == local_max) & (dist_smooth > 2)).astype(np.uint8) * 255
    cores      = cv2.dilate(cores, np.ones((3, 3)))
    num_labels, comp_map = cv2.connectedComponents(cores)

    queue      = deque()
    region_map = np.zeros_like(comp_map, dtype=np.int32)
    ys, xs     = np.where(comp_map > 0)
    for y, x in zip(ys, xs):
        queue.append((x, y, comp_map[y, x]))
        region_map[y, x] = comp_map[y, x]
    while queue:
        x, y, cid = queue.popleft()
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx2, ny2 = x + dx, y + dy
            if 0 <= nx2 < width and 0 <= ny2 < height:
                if working_free[ny2, nx2] > 0 and region_map[ny2, nx2] == 0:
                    region_map[ny2, nx2] = cid
                    queue.append((nx2, ny2, cid))

    # ── Map OCR labels to BFS regions (identical to v4) ──────────────────────
    core_to_labels = defaultdict(list)
    for idx, room in enumerate(rooms_raw):
        sx, sy = to_px(room['x'], room['z'])
        sx = int(np.clip(sx, 0, width - 1))
        sy = int(np.clip(sy, 0, height - 1))
        cid = region_map[sy, sx]
        if cid == 0:
            found = 0
            for r in range(1, int(min(width, height) * 0.1), 2):
                y_min = max(0, sy - r); y_max = min(height - 1, sy + r)
                x_min = max(0, sx - r); x_max = min(width - 1,  sx + r)
                roi = region_map[y_min:y_max + 1, x_min:x_max + 1]
                if np.any(roi > 0):
                    ys_r, xs_r = np.where(roi > 0)
                    dd = (xs_r - (sx - x_min)) ** 2 + (ys_r - (sy - y_min)) ** 2
                    mi = int(np.argmin(dd))
                    found = region_map[int(ys_r[mi] + y_min), int(xs_r[mi] + x_min)]
                    break
            cid = found
        if cid > 0:
            core_to_labels[cid].append((idx, sx, sy))

    # ── Per-room masks via Voronoi split when a region holds multiple labels ──
    room_masks = {}
    for cid, labels in core_to_labels.items():
        core_mask = (region_map == cid)
        if len(labels) == 1:
            room_masks[labels[0][0]] = core_mask
        else:
            ys2, xs2   = np.where(core_mask)
            pts        = np.column_stack((xs2, ys2))
            label_pts  = np.array([[l[1], l[2]] for l in labels])
            dists_arr  = np.sum((pts[:, None, :] - label_pts[None, :, :]) ** 2, axis=2)
            closest    = np.argmin(dists_arr, axis=1)
            for li, lbl in enumerate(labels):
                sub = np.zeros_like(core_mask, dtype=bool)
                sub[ys2[closest == li], xs2[closest == li]] = True
                room_masks[lbl[0]] = sub

    # ── LIR per room mask (replaces expand_from_point + working_free erasure) ─
    tile_margin = max(2, min(int(wall_thickness * 0.12), 4))
    margin_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (tile_margin * 2 + 1, tile_margin * 2 + 1)
    )
    min_area = max(50, int(height * width * 0.0005))

    sorted_rooms = sorted(enumerate(rooms_raw), key=lambda kv: kv[1]['name'].lower())
    final_rooms  = []

    for idx, room in sorted_rooms:
        if idx not in room_masks:
            continue
            
        bounded = room_masks[idx].astype(np.uint8) * 255
        
        # Erode strictly to avoid touching walls (creates spacing)
        tile_margin = max(4, int(wall_thickness * 0.4))
        margin_kernel_small = cv2.getStructuringElement(cv2.MORPH_RECT, (tile_margin * 2 + 1, tile_margin * 2 + 1))
        safe = cv2.erode(bounded, margin_kernel_small)
        
        rect = _lir_cropped(safe)
        if rect is None:
            # Fallback with smaller margin if room is too small
            safe2 = cv2.erode(bounded, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
            rect  = _lir_cropped(safe2)
            
        if rect is None:
            continue
            
        x1, y1, x2, y2 = rect
        
        # Ensure we have a valid rectangle size
        if x2 <= x1 or y2 <= y1 or (x2 - x1) * (y2 - y1) < min_area:
            continue
            
        rx1, rz1 = to_3d(x1, y1)
        rx2, rz2 = to_3d(x2, y2)
        
        final_rooms.append({
            "name":    room['name'],
            "x":       room['x'],
            "z":       room['z'],
            "w":       abs(rx2 - rx1),
            "h":       abs(rz2 - rz1),
            "polygon": [
                {"x": rx1, "z": rz1}, {"x": rx2, "z": rz1},
                {"x": rx2, "z": rz2}, {"x": rx1, "z": rz2},
            ]
        })

    if not final_rooms:
        return _expand_rooms_v4(rooms_raw, wall_mask, wall_thickness, height, width)

    return final_rooms


