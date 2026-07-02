"""Precise wall geometry extraction.

Walls in a floor plan are the *thick* ink strokes; furniture outlines, text,
dimension lines, hatching and door-swing arcs are all drawn thin. Filtering by
per-pixel stroke width (distance transform) recovers the exact wall strokes
without relying on room labels or an AI model.

On top of the wall mask this module:
  * detects door/window openings by pairing wall endpoints across small gaps
    and seals them, producing a watertight "sealed" mask;
  * segments the free interior space into disjoint room regions;
  * snaps AI-named boxes onto those regions so a room tile can never cross a
    wall, overlap a neighbour, or leave the building.
"""
import numpy as np
import cv2

from app.services.vision.algorithms import _lir_cropped


def _skeletonize(mask_u8):
    try:
        from cv2 import ximgproc
        return ximgproc.thinning(mask_u8, thinningType=ximgproc.THINNING_ZHANGSUEN)
    except (ImportError, AttributeError):
        skeleton = np.zeros_like(mask_u8)
        temp = mask_u8.copy()
        cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        for _ in range(200):
            eroded = cv2.erode(temp, cross)
            opened = cv2.dilate(eroded, cross)
            skeleton = cv2.bitwise_or(skeleton, cv2.subtract(temp, opened))
            temp = eroded
            if cv2.countNonZero(temp) == 0:
                break
        return skeleton


def _binarize(gray):
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    dark_ratio = np.count_nonzero(thresh) / thresh.size
    if dark_ratio > 0.45 or dark_ratio < 0.02:
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
            blockSize=51, C=15,
        )
    return thresh


def _estimate_wall_thickness(dist, img_min):
    # Ink thicker than ~3px is dominated by walls, so a high percentile of the
    # stroke-width distribution lands on the structural wall thickness.
    widths = dist[dist >= 1.6] * 2.0
    if widths.size < 100:
        return max(5.0, img_min * 0.012)
    t = float(np.percentile(widths, 90))
    return float(max(4.0, min(t, img_min * 0.08)))


def _endpoint_directions(skeleton01, endpoints, radius):
    """Outward direction of each wall endpoint (unit vector pointing away
    from the wall body)."""
    h, w = skeleton01.shape
    dirs = []
    for (ex, ey) in endpoints:
        x1, y1 = max(0, ex - radius), max(0, ey - radius)
        x2, y2 = min(w, ex + radius + 1), min(h, ey + radius + 1)
        ys, xs = np.nonzero(skeleton01[y1:y2, x1:x2])
        xs = xs + x1; ys = ys + y1
        if len(xs) < 2:
            dirs.append(None)
            continue
        vx = float(np.mean(xs) - ex)
        vy = float(np.mean(ys) - ey)
        n = np.hypot(vx, vy)
        if n < 1e-6:
            dirs.append(None)
            continue
        dirs.append((-vx / n, -vy / n))  # outward = away from the wall mass
    return dirs


def _seal_openings(wall_mask, t, building_mask=None):
    """Bridge door/window-sized gaps between wall ends. Returns the sealed
    mask and the list of bridge segments (the detected openings)."""
    height, width = wall_mask.shape
    inside = wall_mask if building_mask is None else cv2.bitwise_and(wall_mask, building_mask)
    sk = _skeletonize(inside)
    sk01 = (sk > 0).astype(np.uint8)

    nb_kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)
    neighbours = cv2.filter2D(sk01, -1, nb_kernel, borderType=cv2.BORDER_CONSTANT)
    ys, xs = np.nonzero((sk01 == 1) & (neighbours == 1))
    endpoints = list(zip(xs.tolist(), ys.tolist()))

    radius = max(4, int(round(1.2 * t)))
    dirs = _endpoint_directions(sk01, endpoints, radius)

    gap_max = 6.5 * t
    bridges = []
    used = set()

    # Pass 1: endpoint-to-endpoint bridges along the wall direction
    candidates = []
    for i in range(len(endpoints)):
        if dirs[i] is None:
            continue
        for j in range(i + 1, len(endpoints)):
            if dirs[j] is None:
                continue
            ax, ay = endpoints[i]; bx, by = endpoints[j]
            d = np.hypot(bx - ax, by - ay)
            if d < 2 or d > gap_max:
                continue
            ux, uy = (bx - ax) / d, (by - ay) / d
            # bridge must leave A outward and arrive at B against its outward
            if ux * dirs[i][0] + uy * dirs[i][1] < 0.65:
                continue
            if -ux * dirs[j][0] - uy * dirs[j][1] < 0.65:
                continue
            candidates.append((d, i, j))
    candidates.sort()
    for d, i, j in candidates:
        if i in used or j in used:
            continue
        used.add(i); used.add(j)
        bridges.append((endpoints[i][0], endpoints[i][1], endpoints[j][0], endpoints[j][1]))

    # Pass 2: remaining endpoints ray-march outward until they hit a wall face
    # (door openings that end against a perpendicular wall). Hitting a face
    # along the wall's own direction is strong evidence, so the reach is wider.
    face_gap_max = 10.0 * t
    for i, (ex, ey) in enumerate(endpoints):
        if i in used or dirs[i] is None:
            continue
        ox, oy = dirs[i]
        for step in range(3, int(face_gap_max)):
            px = int(round(ex + ox * step)); py = int(round(ey + oy * step))
            if px < 0 or py < 0 or px >= width or py >= height:
                break
            if wall_mask[py, px]:
                bridges.append((ex, ey, px, py))
                used.add(i)
                break

    sealed = wall_mask.copy()
    bt = max(3, int(round(t)))
    for (x1, y1, x2, y2) in bridges:
        cv2.line(sealed, (x1, y1), (x2, y2), 255, bt)

    # Backstop for hairline breaks the endpoint pass missed
    hk = max(3, int(round(1.2 * t)))
    sealed = cv2.morphologyEx(sealed, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (hk, 3)))
    sealed = cv2.morphologyEx(sealed, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (3, hk)))

    doors = [b for b in bridges if np.hypot(b[2] - b[0], b[3] - b[1]) >= 1.2 * t]
    return sealed, doors


def _scrub_dense_blobs(wall, t):
    """Erase plant/ornament symbols even when they touch a wall: their ink is
    locally dense, while walls are lines whose local density stays low even at
    junctions (~0.3)."""
    k = int(round(7 * t))
    if k % 2 == 0:
        k += 1
    density = cv2.boxFilter((wall > 0).astype(np.float32), -1, (k, k),
                            borderType=cv2.BORDER_CONSTANT)
    return np.where(density > 0.42, 0, wall).astype(np.uint8)


def _prune_components(wall, t, img_min):
    """Drop short strokes (labels, symbols) and compact dense blobs. Wall
    chunks between windows are short, so the length bar must stay low (~1.5t)
    or perimeter walls with many windows disintegrate."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(wall, 8)
    min_len = max(1.2 * t, img_min * 0.012)
    keep = np.zeros(n, dtype=bool)
    for i in range(1, n):
        cw = stats[i, cv2.CC_STAT_WIDTH]; ch = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        if max(cw, ch) < min_len or area < 0.8 * t * t:
            continue
        # Plant/ornament: compact box, both dimensions blobby, densely inked
        if (max(cw, ch) < 8 * t and min(cw, ch) >= 2.5 * t
                and area / float(cw * ch) > 0.28):
            continue
        keep[i] = True
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def _wall_mask_thick(thresh, dist, t, img_min):
    """Stroke-width filter: keep only ink whose local width is wall-like.
    core_r keeps thin interior partitions (~1/3 of the main wall thickness)
    while dropping furniture outlines, text and dimension lines."""
    core_r = max(1.6, 0.16 * t)
    cores = (dist >= core_r).astype(np.uint8) * 255
    grow = int(np.ceil(core_r)) + 1
    grow_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    wall = cv2.bitwise_and(cv2.dilate(cores, grow_kernel), thresh)
    wall = _scrub_dense_blobs(wall, t)
    return _prune_components(wall, t, img_min)


def _wall_mask_thin(thresh, t, img_min):
    """Fallback for plans whose walls are thin lines (same weight as
    furniture): keep only long straight horizontal/vertical ink runs."""
    run_len = max(25, int(img_min * 0.04))
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (run_len, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, run_len))
    h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)
    v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)
    wall = cv2.bitwise_or(h_lines, v_lines)
    return _prune_components(wall, t, img_min)


def _flood_footprint(sealed, height, width):
    """Building = everything a border flood on the sealed mask cannot reach.
    Robust to sparse walls; naturally excludes open-air balconies/porches."""
    free = (sealed == 0).astype(np.uint8)
    padded = cv2.copyMakeBorder(free, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=1)
    ff_mask = np.zeros((height + 4, width + 4), dtype=np.uint8)
    cv2.floodFill(padded, ff_mask, (0, 0), 2)
    outside = padded[1:-1, 1:-1] == 2
    building = np.where(outside, 0, 255).astype(np.uint8)

    n, labels, stats, _ = cv2.connectedComponentsWithStats(building, 4)
    if n < 2:
        return None
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[best, cv2.CC_STAT_AREA] < 0.15 * height * width:
        return None
    building_mask = np.where(labels == best, 255, 0).astype(np.uint8)
    bx, by = stats[best, cv2.CC_STAT_LEFT], stats[best, cv2.CC_STAT_TOP]
    bw, bh = stats[best, cv2.CC_STAT_WIDTH], stats[best, cv2.CC_STAT_HEIGHT]
    return building_mask, (int(bx), int(by), int(bx + bw), int(by + bh))


def extract_wall_geometry(gray):
    """Full geometric analysis of a floor plan image.

    Returns None when no plausible wall structure is found, otherwise a dict:
      wall_thickness, wall_mask, sealed_mask, building_mask, bbox,
      doors [(x1,y1,x2,y2)...], label_map (int32, 0 = not a room),
      regions [{id, area, bbox, cx, cy}...]
    """
    height, width = gray.shape[:2]
    img_min = min(height, width)

    thresh = _binarize(gray)
    dist = cv2.distanceTransform(thresh, cv2.DIST_L2, 5)
    t = _estimate_wall_thickness(dist, img_min)

    wall = _wall_mask_thick(thresh, dist, t, img_min)
    sealed = doors = footprint = None
    if cv2.countNonZero(wall) >= 50:
        sealed, doors = _seal_openings(wall, t)
        footprint = _flood_footprint(sealed, height, width)
    thin_mode = False
    if footprint is None:
        # Thin-line drawing style: stroke width can't separate walls from
        # furniture, fall back to long straight runs.
        thin_mode = True
        t = max(4.0, min(t, img_min * 0.02))
        wall = _wall_mask_thin(thresh, t, img_min)
        if cv2.countNonZero(wall) < 50:
            return None
        sealed, doors = _seal_openings(wall, t)
        footprint = _flood_footprint(sealed, height, width)
        if footprint is None:
            return None
    building_mask, (bx, by, bx2, by2) = footprint

    # Rooms behind door-plus-sized openings (wide passages, rooms open to a
    # balcony) leak to the outside in the strict flood. A relaxed flood over a
    # dilated sealed mask encloses them; truly open air (balcony with no
    # walls at all) still stays outside.
    relax = int(round(3.2 * t))
    if relax >= 2:
        dilated = cv2.dilate(sealed, cv2.getStructuringElement(cv2.MORPH_RECT, (relax, relax)))
        relaxed = _flood_footprint(dilated, height, width)
        if relaxed is not None:
            # Undo the outward bloat the dilation added: dilation with a k-kernel
            # expands ~k/2, erosion with a k-kernel removes ~k/2 — same k.
            shave = relax + 3
            relaxed_mask = cv2.erode(relaxed[0],
                                     cv2.getStructuringElement(cv2.MORPH_RECT, (shave, shave)))
            building_mask = cv2.bitwise_or(building_mask, relaxed_mask)
            ys2, xs2 = np.nonzero(building_mask)
            bx, by, bx2, by2 = int(xs2.min()), int(ys2.min()), int(xs2.max()), int(ys2.max())
    bw, bh = bx2 - bx, by2 - by

    # Remove ink outside the building (compass, legends, dimension text)
    outside_guard = cv2.dilate(building_mask,
                               cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
    wall = cv2.bitwise_and(wall, outside_guard)

    # Disjoint room regions = connected free space inside the sealed envelope
    free = cv2.bitwise_and(cv2.bitwise_not(sealed), building_mask)
    n_reg, label_map, reg_stats, reg_centroids = cv2.connectedComponentsWithStats(free, 4)
    min_area = max(25.0, 4.0 * t * t)
    if thin_mode:
        # Thin-line plans keep furniture rectangles as fake enclosures; only
        # room-scale regions are trustworthy there.
        min_area = max(min_area, 0.008 * float(np.count_nonzero(building_mask)))
    regions = []
    label_map = label_map.astype(np.int32)
    for i in range(1, n_reg):
        area = float(reg_stats[i, cv2.CC_STAT_AREA])
        if area < min_area:
            label_map[label_map == i] = 0
            continue
        regions.append({
            "id": int(i),
            "area": area,
            "bbox": (int(reg_stats[i, cv2.CC_STAT_LEFT]), int(reg_stats[i, cv2.CC_STAT_TOP]),
                     int(reg_stats[i, cv2.CC_STAT_WIDTH]), int(reg_stats[i, cv2.CC_STAT_HEIGHT])),
            "cx": float(reg_centroids[i][0]),
            "cy": float(reg_centroids[i][1]),
        })

    return {
        "wall_thickness": float(t),
        "wall_mask": wall,
        "sealed_mask": sealed,
        "building_mask": building_mask,
        "bbox": (bx, by, bx + bw, by + bh),
        "doors": doors,
        "label_map": label_map,
        "regions": regions,
    }


def _region_tile(mask_u8, name, height, width):
    """Build a room tile (rect anchor + polygon outline) from a region mask."""
    aspect = height / width

    def to_3d(px, py):
        return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)

    rect = _lir_cropped(mask_u8)
    if rect is None:
        return None
    rx1, ry1, rx2, ry2 = rect
    cx3, cz3 = to_3d((rx1 + rx2) / 2, (ry1 + ry2) / 2)
    px1, pz1 = to_3d(rx1, ry1)
    px2, pz2 = to_3d(rx2 + 1, ry2 + 1)

    # Tiles are axis-aligned rectangles (largest inscribed in the region) —
    # raw region contours read as random shapes in the UI.
    polygon = [{"x": px1, "z": pz1}, {"x": px2, "z": pz1},
               {"x": px2, "z": pz2}, {"x": px1, "z": pz2}]

    return {
        "name": name,
        "x": cx3, "z": cz3,
        "w": abs(px2 - px1), "h": abs(pz2 - pz1),
        "polygon": polygon,
    }


def snap_rooms_to_regions(ai_rooms, geometry, height, width):
    """Assign AI/OCR-named boxes to geometric room regions.

    Region geometry is authoritative: every tile is carved from exactly one
    region (or a nearest-seed split of a shared region), so tiles are disjoint
    and wall-bounded by construction. AI boxes only contribute names.
    """
    aspect = height / width
    label_map = geometry["label_map"]
    regions = geometry["regions"]
    building_mask = geometry["building_mask"]
    if not regions:
        return []

    def to_px_box(r):
        cx = (r["x"] + 10) / 20 * width
        cy = (r["z"] / aspect + 10) / 20 * height
        wpx = max(4.0, r.get("w", 2.0) / 20 * width)
        hpx = max(4.0, r.get("h", 2.0) / (20 * aspect) * height)
        x1 = int(max(0, cx - wpx / 2)); y1 = int(max(0, cy - hpx / 2))
        x2 = int(min(width, cx + wpx / 2)); y2 = int(min(height, cy + hpx / 2))
        return x1, y1, x2, y2

    max_region_id = int(label_map.max())
    region_by_id = {r["id"]: r for r in regions}

    # Score every AI room against every region by pixel overlap
    assignments = {}   # region_id -> list of (score, ai_idx)
    ai_boxes = []
    ai_scores = []
    for idx, room in enumerate(ai_rooms):
        x1, y1, x2, y2 = to_px_box(room)
        ai_boxes.append((x1, y1, x2, y2))
        best = (0.0, None)
        if x2 > x1 and y2 > y1:
            window = label_map[y1:y2, x1:x2]
            counts = np.bincount(window.ravel(), minlength=max_region_id + 1)
            box_area = (x2 - x1) * (y2 - y1)
            for rid, reg in region_by_id.items():
                ov = counts[rid] if rid < len(counts) else 0
                if ov == 0:
                    continue
                # A pocket much smaller than the box scores a perfect overlap
                # ratio while the real room scores less — don't let it win.
                if reg["area"] < 0.08 * box_area:
                    continue
                score = ov / min(box_area, reg["area"])
                if score > best[0]:
                    best = (score, rid)
        ai_scores.append(best)
        if best[1] is not None and best[0] >= 0.15:
            assignments.setdefault(best[1], []).append((best[0], idx))

    tiles = []
    claimed_regions = set()

    for rid, entries in assignments.items():
        claimed_regions.add(rid)
        entries.sort(reverse=True)
        entries = entries[:6]
        region_mask = (label_map == rid).astype(np.uint8) * 255
        if len(entries) == 1:
            tile = _region_tile(region_mask, ai_rooms[entries[0][1]]["name"], height, width)
            if tile:
                tiles.append(tile)
            continue
        # Several AI rooms landed on one open-plan region: split it between
        # their seed centers so each named area gets its own share.
        ys, xs = np.nonzero(region_mask)
        centers = []
        for _, idx in entries:
            x1, y1, x2, y2 = ai_boxes[idx]
            centers.append(((x1 + x2) / 2, (y1 + y2) / 2))
        centers = np.array(centers)
        d2 = (xs[None, :] - centers[:, 0:1]) ** 2 + (ys[None, :] - centers[:, 1:2]) ** 2
        owner = np.argmin(d2, axis=0)
        for k, (_, idx) in enumerate(entries):
            sub = np.zeros((height, width), dtype=np.uint8)
            sel = owner == k
            sub[ys[sel], xs[sel]] = 255
            tile = _region_tile(sub, ai_rooms[idx]["name"], height, width)
            if tile:
                tiles.append(tile)

    # Regions no AI room claimed still exist physically: ship them unnamed.
    # Tiny unclaimed pockets (wall niches, artifacts) are noise — skip them.
    building_area = float(np.count_nonzero(building_mask))
    min_room_area = max(0.012 * building_area, 4.0 * geometry["wall_thickness"] ** 2)
    for reg in regions:
        if reg["id"] in claimed_regions:
            continue
        if reg["area"] < min_room_area:
            continue
        region_mask = (label_map == reg["id"]).astype(np.uint8) * 255
        tile = _region_tile(region_mask, "Room", height, width)
        if tile:
            tiles.append(tile)

    # AI rooms with no region are kept only if they are genuinely outdoor
    # areas (balcony/porch outside the sealed envelope).
    outdoor_claim = np.zeros((height, width), dtype=np.uint8)
    for idx, room in enumerate(ai_rooms):
        score, rid = ai_scores[idx]
        if rid is not None and score >= 0.15:
            continue
        x1, y1, x2, y2 = ai_boxes[idx]
        if x2 <= x1 or y2 <= y1:
            continue
        box_area = (x2 - x1) * (y2 - y1)
        inside = np.count_nonzero(building_mask[y1:y2, x1:x2])
        if inside > 0.5 * box_area:
            continue  # indoor hallucination: geometry says there is no room here
        outdoor = np.zeros((height, width), dtype=np.uint8)
        outdoor[y1:y2, x1:x2] = 255
        outdoor[building_mask > 0] = 0
        outdoor[outdoor_claim > 0] = 0
        outdoor[geometry["sealed_mask"] > 0] = 0
        tile = _region_tile(outdoor, room["name"], height, width)
        if tile:
            tiles.append(tile)
            ox1, oy1, ox2, oy2 = to_px_box({"x": tile["x"], "z": tile["z"],
                                            "w": tile["w"], "h": tile["h"]})
            cv2.rectangle(outdoor_claim, (ox1, oy1), (ox2, oy2), 255, -1)

    return tiles
