import os
import cv2
import numpy as np
import math
from app.core.config import PIPELINE_VERSION
from app.services.vision.algorithms import _expand_rooms_v4, _expand_rooms_v5, _expand_rooms_v6, _expand_rooms_v7, _expand_rooms_ai_clip, _expand_rooms_v8_polygons
from app.services.vision.core import _extract_rooms
from app.services.vision.walls import extract_wall_geometry, snap_rooms_to_regions
from typing import Tuple, List, Dict, Any

def process_image(img_bytes: bytes):
    yield (5, "Decoding blueprint...")
    # ── Decode ───────────────────────────────────────────────────────────────
    nparr = np.frombuffer(img_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")

    gray          = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    height, width = img.shape[:2]
    img_min       = min(height, width)
    aspect        = height / width

    yield (15, "Applying adaptive thresholding...")
    # ── Fix 1: Adaptive thresholding ─────────────────────────────────────────
    _, thresh  = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    dark_ratio = np.sum(thresh > 0) / thresh.size
    if dark_ratio > 0.45 or dark_ratio < 0.02:
        thresh = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=51,
            C=15,
        )

    yield (25, "Extracting structural walls...")
    # ── Fix 2: Measure wall thickness → size kernels relative to it ──────────
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    thicknesses = []
    for cnt in contours:
        area      = cv2.contourArea(cnt)
        perimeter = cv2.arcLength(cnt, True)
        if perimeter > 0 and area > 100:
            t = (2 * area) / perimeter
            if 3 < t < 60:
                thicknesses.append(t)
    wall_thickness = int(np.median(thicknesses)) if thicknesses else max(5, int(img_min * 0.01))

    # Erase tiny text and noise before morphology
    # We lowered this threshold from 0.05 to 0.01 to prevent deleting 
    # short wall segments (walls interrupted by doors/windows).
    text_erased_thresh = np.zeros_like(thresh)
    for cnt in contours:
        if cv2.arcLength(cnt, True) > img_min * 0.01:
            cv2.drawContours(text_erased_thresh, [cnt], -1, 255, -1)

    # Opening: erase anything thinner than 50 % of wall thickness (furniture)
    open_k      = max(3, int(wall_thickness * 0.5))
    open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_k, open_k))
    structural_mask = cv2.morphologyEx(text_erased_thresh, cv2.MORPH_OPEN, open_kernel)

    # Closing: bridge small gaps in walls (doors, intersections)
    close_k      = max(5, int(wall_thickness * 0.8))
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (close_k, close_k))
    cleaned      = cv2.morphologyEx(structural_mask, cv2.MORPH_CLOSE, close_kernel)

    yield (32, "Extracting precise wall geometry...")
    # ── Precise wall/door/region geometry (walls.py) ─────────────────────────
    geometry = None
    try:
        geometry = extract_wall_geometry(gray)
        if geometry is not None:
            print(f"Wall geometry: t={geometry['wall_thickness']:.1f} "
                  f"doors={len(geometry['doors'])} regions={len(geometry['regions'])}")
    except Exception as e:
        print("Wall geometry error:", e)

    # The precise stroke mask gives far cleaner centerlines than the legacy
    # morphology mask when it is available.
    skeleton_src = geometry["wall_mask"] if geometry is not None else cleaned

    yield (35, "Generating geometric skeleton...")
    # ── Fix 3: Skeletonize → single-pixel wall centerlines ───────────────────
    try:
        from cv2 import ximgproc as _ximgproc
        skeleton = _ximgproc.thinning(skeleton_src, thinningType=_ximgproc.THINNING_ZHANGSUEN)
    except (ImportError, AttributeError):
        # Fallback: iterative erosion skeleton (no extra dependency needed)
        skeleton  = np.zeros_like(skeleton_src)
        temp      = skeleton_src.copy()
        cross     = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        max_iters = max(30, wall_thickness * 2)   # cap prevents infinite loop
        for _ in range(max_iters):
            eroded = cv2.erode(temp, cross)
            opened = cv2.dilate(eroded, cross)
            diff   = cv2.subtract(temp, opened)
            skeleton = cv2.bitwise_or(skeleton, diff)
            temp   = eroded.copy()
            if cv2.countNonZero(temp) == 0:
                break

    # Slight dilation so Canny has edges to detect on the 1-px skeleton
    skeleton = cv2.dilate(skeleton, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)))

    yield (45, "Detecting architectural lines...")
    # ── Fix 4: Improved HoughLinesP ───────────────────────────────────────────
    edges           = cv2.Canny(skeleton, 30, 100, apertureSize=3)
    min_line_length = max(30, int(img_min * 0.04))
    max_line_gap    = max(25, int(img_min * 0.06))   # 3× larger → survives door gaps
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 360,   # 0.5° precision (vs 1°) for straighter wall detection
        threshold=30,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )

    # ── Fix 5: Angle filter — keep only near-horizontal / near-vertical ───────
    ANGLE_TOL = 12  # degrees

    def is_architectural(x1, y1, x2, y2):
        if x1 == x2 and y1 == y2:
            return False
        angle  = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
        near_h = angle <= ANGLE_TOL or angle >= (180 - ANGLE_TOL)
        near_v = (90 - ANGLE_TOL) <= angle <= (90 + ANGLE_TOL)
        return near_h or near_v

    raw_lines = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if is_architectural(x1, y1, x2, y2):
                raw_lines.append((x1, y1, x2, y2))

    # ── Fix 6: Snap to axis → collinear segment merging ──────────────────────
    def snap_to_axis(segs):
        result = []
        for (x1, y1, x2, y2) in segs:
            angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
            if angle <= ANGLE_TOL or angle >= (180 - ANGLE_TOL):      # horizontal
                avg_y = (y1 + y2) // 2
                result.append((min(x1, x2), avg_y, max(x1, x2), avg_y))
            else:                                                       # vertical
                avg_x = (x1 + x2) // 2
                result.append((avg_x, min(y1, y2), avg_x, max(y1, y2)))
        return result

    def merge_collinear(segs):
        BUCKET_TOL = max(6, int(img_min * 0.006))   # perpendicular grouping tolerance
        merge_gap  = max(20, int(img_min * 0.04))    # max pixel gap to bridge

        h_segs = [(x1, y1, x2, y2) for (x1, y1, x2, y2) in segs if y1 == y2]
        v_segs = [(x1, y1, x2, y2) for (x1, y1, x2, y2) in segs if x1 == x2]

        def merge_group(group, is_horizontal):
            buckets = {}
            for seg in group:
                x1, y1, x2, y2 = seg
                key = (y1 if is_horizontal else x1) // BUCKET_TOL
                buckets.setdefault(key, []).append(seg)
            merged = []
            for bucket_segs in buckets.values():
                if is_horizontal:
                    bucket_segs.sort(key=lambda s: s[0])
                    cx1, cy, cx2, _ = bucket_segs[0]
                    for (x1, y1, x2, y2) in bucket_segs[1:]:
                        if x1 <= cx2 + merge_gap:
                            cx2 = max(cx2, x2)
                        else:
                            merged.append((cx1, cy, cx2, cy))
                            cx1, cy, cx2 = x1, y1, x2
                    merged.append((cx1, cy, cx2, cy))
                else:
                    bucket_segs.sort(key=lambda s: s[1])
                    cx, cy1, _, cy2 = bucket_segs[0]
                    for (x1, y1, x2, y2) in bucket_segs[1:]:
                        if y1 <= cy2 + merge_gap:
                            cy2 = max(cy2, y2)
                        else:
                            merged.append((cx, cy1, cx, cy2))
                            cx, cy1, cy2 = x1, y1, y2
                    merged.append((cx, cy1, cx, cy2))
            return merged

        return merge_group(h_segs, True) + merge_group(v_segs, False)

    snapped = snap_to_axis(raw_lines)
    merged  = merge_collinear(snapped)

    yield (55, "Normalizing 3D space...")
    # ── Normalize to 3D space ─────────────────────────────────────────────────
    walls = []
    for (x1, y1, x2, y2) in merged:
        nx1 = (x1 / width)  * 20 - 10
        nz1 = ((y1 / height) * 20 - 10) * aspect
        nx2 = (x2 / width)  * 20 - 10
        nz2 = ((y2 / height) * 20 - 10) * aspect
        walls.append({"points": [{"x": float(nx1), "z": float(nz1)},
                                  {"x": float(nx2), "z": float(nz2)}]})

    def get_rooms_raw():
        nonlocal img, height, width
        raw = _extract_rooms(img, height, width)
        min_dist = int(min(height, width) * 0.05)
        deduped = []
        for r in raw:
            too_close = False
            for kept in deduped:
                dx = abs(r['x'] - kept['x'])
                dy = abs(r['z'] - kept['z'])
                if (dx / 20 * width) ** 2 + (dy / 20 * height) ** 2 < min_dist ** 2:
                    too_close = True
                    break
            if not too_close:
                deduped.append(r)
        return deduped

    yield (60, "Running AI Vision extraction...")
    if PIPELINE_VERSION == "v7":
        rooms = None
        import base64

        # Downscaled JPEG: the model only needs to read labels, and a 10x
        # smaller payload cuts round-trip time. Coordinates are 0-1000
        # normalized, so resolution doesn't matter.
        ai_img = img
        if max(height, width) > 1024:
            s = 1024 / max(height, width)
            ai_img = cv2.resize(img, (int(width * s), int(height * s)), interpolation=cv2.INTER_AREA)
        ok_enc, jpeg_buf = cv2.imencode('.jpg', ai_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        ai_bytes = jpeg_buf.tobytes() if ok_enc else img_bytes
        base64_image = base64.b64encode(ai_bytes).decode('utf-8')

        # 1. Try Nemotron First (Reasoning / Primary)
        try:
            from openai import OpenAI
            import json
            
            client = OpenAI(
              base_url="https://integrate.api.nvidia.com/v1",
              api_key=os.environ.get("NVIDIA_API_KEY", ""),
              timeout=20.0,
              max_retries=0,
            )
            
            prompt = """
Your role: Expert architectural blueprint digitizer and 3D scene generator.
Your task: Analyze the provided 2D floorplan image and segment EVERY interior space into bounding boxes — one box per room or distinct area.

COORDINATE SYSTEM:
- The image is mapped to a 1000x1000 grid.
- (0, 0) is the TOP-LEFT corner. (1000, 1000) is the BOTTOM-RIGHT corner.
- x increases left → right (columns). y increases top → bottom (rows).

OUTPUT FORMAT:
Return a strictly valid JSON array. Each object must have exactly these keys:
  "name"  — the room label as written on the blueprint (e.g. "Bedroom 1", "Living Room", "Hallway"). Use "Room" if unlabeled.
  "xmin"  — left edge of the box (0–1000).
  "ymin"  — top edge of the box (0–1000).
  "xmax"  — right edge of the box (0–1000).
  "ymax"  — bottom edge of the box (0–1000).

EXAMPLE (structure only — do not copy these values):
[
  {"name": "Living Room", "xmin": 50, "ymin": 60, "xmax": 420, "ymax": 390},
  {"name": "Kitchen",     "xmin": 420, "ymin": 60, "xmax": 700, "ymax": 390},
  {"name": "Bedroom 1",   "xmin": 50, "ymin": 390, "xmax": 380, "ymax": 700}
]

CRITICAL RULES — follow all of them exactly:

1. COVER THE COMPLETE ROOM (WALL-TO-WALL):
   - Your bounding box MUST stretch to cover the entire empty, walkable interior space of the room.
   - Do not make the boxes too small! They should go right up to the inner edges of the walls.

2. DO NOT BLEED OVER WALLS & DO NOT GO OUTSIDE:
   - While you must cover the complete room, the box MUST stop flush against the inner edge of the wall.
   - A box MUST NEVER pass or bleed through a thick structural wall into an adjacent room.
   - Adjacent rooms must not overlap.
   - MUST NEVER go outside of the outer exterior walls of the building into the blank background space.

3. COVER ALL SPACES:
   - Include hallways, corridors, bathrooms, closets, staircases, and utility rooms.
   - For L-shaped rooms, provide a bounding box that covers the primary largest rectangular area of that room.

Return ONLY the raw JSON array. No markdown fences, no comments, no trailing commas, no extra keys.
            """
            yield (65, "AI Analyzing floorplan (Nemotron)...")
            completion = client.chat.completions.create(
              model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
              messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                            },
                        },
                    ],
                }],
              temperature=0.1,
              top_p=0.95,
              max_tokens=2500,
              # Thinking mode makes vision calls take 90s+ (frequent timeouts) and
              # the wall geometry owns coordinates now — names don't need reasoning.
              extra_body={"chat_template_kwargs":{"enable_thinking":False}},
              stream=False
            )
            
            yield (75, "AI Parsing response...")
            print("Nemotron generation complete.")
                
            full_content = completion.choices[0].message.content
            
            txt = full_content.strip()
            if txt.startswith("```json"): txt = txt[7:]
            if txt.startswith("```"): txt = txt[3:]
            if txt.endswith("```"): txt = txt[:-3]
            
            rooms_data = json.loads(txt.strip())
            if isinstance(rooms_data, dict) and len(rooms_data.keys()) == 1:
                rooms_data = list(rooms_data.values())[0]
                
            if isinstance(rooms_data, list):
                nemotron_rooms = []
                seen_names = set()
                for r in rooms_data:
                    if not isinstance(r, dict):
                        continue
                    try:
                        xmin = float(r.get("xmin", 0))
                        xmax = float(r.get("xmax", 0))
                        ymin = float(r.get("ymin", 0))
                        ymax = float(r.get("ymax", 0))
                    except (TypeError, ValueError):
                        continue
                    # Clamp to the 0-1000 grid the prompt defines
                    xmin = max(0.0, min(xmin, 1000.0))
                    xmax = max(0.0, min(xmax, 1000.0))
                    ymin = max(0.0, min(ymin, 1000.0))
                    ymax = max(0.0, min(ymax, 1000.0))
                    # Degenerate slivers (<0.5% of the grid) are hallucinations
                    if xmax - xmin < 5 or ymax - ymin < 5:
                        continue
                    # A labeled room returned twice is a hallucinated duplicate
                    name = str(r.get("name", "Room")).strip() or "Room"
                    name_key = name.lower()
                    if name_key != "room" and name_key in seen_names:
                        continue
                    seen_names.add(name_key)
                    
                    xmin_3d = (xmin / 1000.0) * 20 - 10
                    xmax_3d = (xmax / 1000.0) * 20 - 10
                    ymin_3d = ((ymin / 1000.0) * 20 - 10) * aspect
                    ymax_3d = ((ymax / 1000.0) * 20 - 10) * aspect
                    
                    
                    orig_x = (xmin_3d + xmax_3d) / 2
                    orig_z = (ymin_3d + ymax_3d) / 2
                    
                    nemotron_rooms.append({
                        "name": name,
                        "x": float(orig_x),
                        "z": float(orig_z),
                        "w": float(abs(xmax_3d - xmin_3d)),
                        "h": float(abs(ymax_3d - ymin_3d)),
                        "polygon": [
                            {"x": float(xmin_3d), "z": float(ymin_3d)},
                            {"x": float(xmax_3d), "z": float(ymin_3d)},
                            {"x": float(xmax_3d), "z": float(ymax_3d)},
                            {"x": float(xmin_3d), "z": float(ymax_3d)}
                        ]
                    })
                if nemotron_rooms:
                    yield (80, "Merging AI rooms with OCR fallbacks...")
                    ocr_fallback = get_rooms_raw()
                    merged_rooms = nemotron_rooms.copy()
                    for ocr_r in ocr_fallback:
                        # Add OCR room only if it's far from any AI room (meaning AI missed it)
                        is_new = True
                        for ai_r in nemotron_rooms:
                            if math.hypot(ocr_r["x"] - ai_r["x"], ocr_r["z"] - ai_r["z"]) < 3.0:
                                is_new = False
                                break
                        if is_new:
                            ocr_r_copy = ocr_r.copy()
                            ocr_r_copy["w"] = 2.0  # Default small box for expansion seed
                            ocr_r_copy["h"] = 2.0
                            merged_rooms.append(ocr_r_copy)
                            
                    yield (85, "Snapping rooms to exact wall geometry...")
                    if geometry is not None and len(geometry["regions"]) >= 2:
                        rooms = snap_rooms_to_regions(merged_rooms, geometry, height, width)
                    if not rooms:
                        rooms = _expand_rooms_v8_polygons(merged_rooms, cleaned, wall_thickness, height, width)
                    print(f"Hybrid Mode: {len(nemotron_rooms)} AI + {len(merged_rooms)-len(nemotron_rooms)} OCR -> {len(rooms)} region-locked rooms.")
        except Exception as e:
            print("Nemotron API error:", e)

        if not rooms:
            try:
                yield (70, "Falling back to Gemini...")
                from app.services.vision.gemini import _extract_rooms_gemini
                rooms_ai = _extract_rooms_gemini(ai_bytes, height, width)
                if rooms_ai and len(rooms_ai) > 0:
                    yield (80, "Merging Gemini rooms with OCR fallbacks...")
                    ocr_fallback = get_rooms_raw()
                    merged_rooms = rooms_ai.copy()
                    for ocr_r in ocr_fallback:
                        is_new = True
                        for ai_r in rooms_ai:
                            if math.hypot(ocr_r["x"] - ai_r["x"], ocr_r["z"] - ai_r["z"]) < 3.0:
                                is_new = False
                                break
                        if is_new:
                            ocr_r_copy = ocr_r.copy()
                            ocr_r_copy["w"] = 2.0
                            ocr_r_copy["h"] = 2.0
                            merged_rooms.append(ocr_r_copy)
                            
                    yield (85, "Snapping rooms to exact wall geometry...")
                    if geometry is not None and len(geometry["regions"]) >= 2:
                        rooms = snap_rooms_to_regions(merged_rooms, geometry, height, width)
                    if not rooms:
                        clipped = _expand_rooms_ai_clip(merged_rooms, cleaned, wall_thickness, height, width)
                        rooms = clipped if clipped else merged_rooms
            except Exception as e:
                print("Gemini integration error:", e)

        if not rooms:
            yield (75, "Falling back to OCR + Rectangular Geometry...")
            rooms_raw = get_rooms_raw()
            merged_rooms = []
            for r in rooms_raw:
                rc = r.copy()
                rc["w"] = 2.0
                rc["h"] = 2.0
                merged_rooms.append(rc)
            if geometry is not None and len(geometry["regions"]) >= 2:
                rooms = snap_rooms_to_regions(merged_rooms, geometry, height, width)
            if not rooms:
                rooms = _expand_rooms_ai_clip(merged_rooms, cleaned, wall_thickness, height, width)
            if not rooms:
                rooms = merged_rooms
    elif PIPELINE_VERSION == "v6":
        rooms = _expand_rooms_v6(get_rooms_raw(), cleaned, wall_thickness, height, width)
    elif PIPELINE_VERSION == "v5":
        rooms = _expand_rooms_v5(get_rooms_raw(), cleaned, wall_thickness, height, width)
    elif PIPELINE_VERSION == "v4":
        rooms = _expand_rooms_v4(get_rooms_raw(), cleaned, wall_thickness, height, width)
    elif PIPELINE_VERSION == 'v3':
        rooms = _expand_rooms_v3(get_rooms_raw(), cleaned, wall_thickness, height, width)
    else:
        rooms = _expand_rooms_v2(get_rooms_raw(), cleaned, wall_thickness, height, width)

    # Detected door/window openings, in the same 3D space as walls
    doors = []
    if geometry is not None:
        for (dx1, dy1, dx2, dy2) in geometry["doors"]:
            doors.append({"points": [
                {"x": float((dx1 / width) * 20 - 10), "z": float(((dy1 / height) * 20 - 10) * aspect)},
                {"x": float((dx2 / width) * 20 - 10), "z": float(((dy2 / height) * 20 - 10) * aspect)},
            ]})

    # Final yield is the result dictionary
    yield {"walls": walls, "rooms": rooms, "doors": doors, "width": width, "height": height}