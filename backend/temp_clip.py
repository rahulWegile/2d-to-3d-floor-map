def _expand_rooms_ai_clip(nemotron_rooms, wall_mask, wall_thickness, height, width):
    """
    Takes Nemotron's raw hallucinated boxes and mathematically clips them so they:
    1. Never overlap each other.
    2. Never pass through structural walls.
    """
    import numpy as np
    import cv2
    
    aspect = height / width
    def to_3d(px, py):
        return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)

    pixel_boxes = []
    for room in nemotron_rooms:
        x_3d = room["x"]
        z_3d = room["z"]
        w_3d = room["w"]
        h_3d = room["h"]
        
        cx = (x_3d + 10) / 20 * width
        cy = (z_3d / aspect + 10) / 20 * height
        w_px = (w_3d / 20) * width
        h_px = (h_3d / (20 * aspect)) * height
        
        x1 = max(0, int(cx - w_px / 2))
        y1 = max(0, int(cy - h_px / 2))
        x2 = min(width, int(cx + w_px / 2))
        y2 = min(height, int(cy + h_px / 2))
        pixel_boxes.append({
            "name": room["name"],
            "x1": x1, "y1": y1, "x2": x2, "y2": y2
        })

    pixel_boxes.sort(key=lambda b: (b["x2"]-b["x1"])*(b["y2"]-b["y1"]))
    
    claimed_mask = np.zeros((height, width), dtype=np.uint8)
    final_rooms = []
    
    for b in pixel_boxes:
        x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
        if x2 <= x1 or y2 <= y1: continue
        
        free_space = np.zeros((height, width), dtype=np.uint8)
        free_space[y1:y2, x1:x2] = 255
        
        free_space[wall_mask > 0] = 0
        free_space[claimed_mask > 0] = 0
        
        margin = max(2, int(wall_thickness * 0.2))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (margin*2+1, margin*2+1))
        safe_space = cv2.erode(free_space, kernel)
        
        rect = _lir_cropped(safe_space)
        if rect is None:
            rect = _lir_cropped(free_space)
            
        if rect is not None:
            rx1, ry1, rx2, ry2 = rect
            cv2.rectangle(claimed_mask, (rx1, ry1), (rx2, ry2), 255, -1)
            
            cx3, cz3 = to_3d((rx1+rx2)/2, (ry1+ry2)/2)
            px1, pz1 = to_3d(rx1, ry1)
            px2, pz2 = to_3d(rx2, ry2)
            
            final_rooms.append({
                "name": b["name"],
                "x": cx3,
                "z": cz3,
                "w": abs(px2 - px1),
                "h": abs(pz2 - pz1),
                "polygon": [{"x": px1, "z": pz1}, {"x": px2, "z": pz1}, {"x": px2, "z": pz2}, {"x": px1, "z": pz2}]
            })
            
    return final_rooms
