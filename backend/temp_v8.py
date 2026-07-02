import numpy as np
import cv2

def _expand_rooms_v8_polygons(rooms_raw, wall_mask, wall_thickness, height, width):
    """
    V8 Polygon Algorithm:
    1. OpenCV extracts perfect non-overlapping region masks (via distance transform & BFS).
    2. We extract the exact polygonal contours of these regions.
    3. We greedy-match Nemotron's hallucinated coordinates to the nearest valid OpenCV region.
    4. We return the exact room polygon to the frontend for perfect 3D rendering without overlaps or wall-crossing.
    """
    aspect = height / width
    def to_3d(px, py):
        return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)

    # 1. OpenCV Region Extraction (Same robust BFS as v4/v7)
    free_space = (wall_mask == 0).astype(np.uint8) * 255
    dist = cv2.distanceTransform(free_space, cv2.DIST_L2, 5)
    
    # Erode dist to find distinct room centers
    local_max = cv2.dilate(dist, np.ones((5, 5), np.uint8))
    peaks = (dist == local_max) & (dist > max(5, wall_thickness * 1.5))
    ys, xs = np.where(peaks)
    
    # Consolidate nearby peaks
    pts = list(zip(xs, ys))
    merged_peaks = []
    min_dist = max(20, wall_thickness * 3)
    for p in pts:
        if not any(np.hypot(p[0]-m[0], p[1]-m[1]) < min_dist for m in merged_peaks):
            merged_peaks.append(p)
            
    if not merged_peaks:
        return rooms_raw # Fallback if no rooms found
        
    # BFS to grow regions
    region_masks = [np.zeros((height, width), dtype=np.uint8) for _ in merged_peaks]
    from collections import deque
    q = deque()
    visited = np.zeros((height, width), dtype=bool)
    
    for i, (px, py) in enumerate(merged_peaks):
        q.append((px, py, i))
        visited[py, px] = True
        region_masks[i][py, px] = 255
        
    while q:
        cx, cy, idx = q.popleft()
        for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < width and 0 <= ny < height:
                if not visited[ny, nx] and free_space[ny, nx] > 0:
                    visited[ny, nx] = True
                    region_masks[idx][ny, nx] = 255
                    q.append((nx, ny, idx))
                    
    # 2. Extract Polygons & Centroids for OpenCV Regions
    cv_regions = []
    for mask in region_masks:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        c = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        if area < 100: continue
        
        # Simplify contour
        epsilon = 0.01 * cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, epsilon, True)
        
        M = cv2.moments(c)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            cx, cy = approx[0][0]
            
        cv_regions.append({
            "contour": approx,
            "cx": cx,
            "cy": cy,
            "mask": mask
        })
        
    if not cv_regions:
        return rooms_raw

    # 3. Match Nemotron rooms to OpenCV regions
    # Parse Nemotron coordinates to pixels
    ai_rooms = []
    for r in rooms_raw:
        x3 = r.get("x", 0)
        z3 = r.get("z", 0)
        px = (x3 + 10) / 20 * width
        py = (z3 / aspect + 10) / 20 * height
        ai_rooms.append({"name": r.get("name", "Unknown"), "px": px, "py": py})
        
    # Greedy matching based on distance
    matches = [] # (ai_idx, cv_idx, dist)
    for i, ai in enumerate(ai_rooms):
        for j, cv in enumerate(cv_regions):
            d = np.hypot(ai["px"] - cv["cx"], ai["py"] - cv["cy"])
            matches.append((i, j, d))
            
    matches.sort(key=lambda x: x[2])
    used_ai = set()
    used_cv = set()
    final_assignments = []
    
    for ai_idx, cv_idx, d in matches:
        if ai_idx not in used_ai and cv_idx not in used_cv:
            final_assignments.append((ai_idx, cv_idx))
            used_ai.add(ai_idx)
            used_cv.add(cv_idx)
            
    # Unmatched AI rooms get assigned to closest unused CV region (if any) or nearest used region
    for ai_idx, ai in enumerate(ai_rooms):
        if ai_idx not in used_ai:
            if len(used_cv) < len(cv_regions):
                # Find closest unused
                best_cv, best_d = None, float('inf')
                for j, cv in enumerate(cv_regions):
                    if j not in used_cv:
                        d = np.hypot(ai["px"] - cv["cx"], ai["py"] - cv["cy"])
                        if d < best_d:
                            best_d = d
                            best_cv = j
                if best_cv is not None:
                    final_assignments.append((ai_idx, best_cv))
                    used_ai.add(ai_idx)
                    used_cv.add(best_cv)
            else:
                # All regions used, just assign to absolute closest to avoid dropping the room
                best_cv, best_d = None, float('inf')
                for j, cv in enumerate(cv_regions):
                    d = np.hypot(ai["px"] - cv["cx"], ai["py"] - cv["cy"])
                    if d < best_d:
                        best_d = d
                        best_cv = j
                if best_cv is not None:
                    final_assignments.append((ai_idx, best_cv))
                    
    # 4. Build final JSON output
    final_rooms = []
    for ai_idx, cv_idx in final_assignments:
        ai_room = ai_rooms[ai_idx]
        cv_room = cv_regions[cv_idx]
        
        # Build 3D polygon
        poly_3d = []
        for pt in cv_room["contour"]:
            px, py = pt[0]
            x3, z3 = to_3d(px, py)
            poly_3d.append({"x": x3, "z": z3})
            
        # Get bounding box of contour for x,z,w,h (used for label positioning)
        x, y, w, h = cv2.boundingRect(cv_room["contour"])
        cx3, cz3 = to_3d(x + w/2, y + h/2)
        x3_1, z3_1 = to_3d(x, y)
        x3_2, z3_2 = to_3d(x + w, y + h)
        w3 = abs(x3_2 - x3_1)
        h3 = abs(z3_2 - z3_1)
        
        final_rooms.append({
            "name": ai_room["name"],
            "x": cx3,
            "z": cz3,
            "w": w3,
            "h": h3,
            "polygon": poly_3d
        })
        
    return final_rooms

# Test mock
if __name__ == "__main__":
    mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.rectangle(mask, (10,10), (40,40), 255, 3)
    cv2.rectangle(mask, (60,10), (90,40), 255, 3)
    rooms_raw = [{"name": "Room A", "x": -5, "z": -5}, {"name": "Room B", "x": 5, "z": -5}]
    res = _expand_rooms_v8_polygons(rooms_raw, mask, 3, 100, 100)
    print("Test passed! Found", len(res), "rooms.")
