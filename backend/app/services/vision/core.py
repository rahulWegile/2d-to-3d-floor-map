import re
import easyocr
reader = easyocr.Reader(['en'], gpu=False, verbose=False)

def _extract_rooms(img, height, width):
    aspect = height / width
    text_results = reader.readtext(img)
    rooms = []
    for bbox, text, conf in text_results:
        text_clean = text.strip()
        is_measurement = (
            bool(re.search(r'\d+\s*[xX*]\s*\d+', text_clean))
            or "'" in text_clean
            or '"' in text_clean
        )
        digits  = sum(c.isdigit() for c in text_clean)
        letters = sum(c.isalpha() for c in text_clean)
        is_numeric = (digits >= letters) if text_clean else True
        if conf > 0.3 and len(text_clean) > 2 and not is_numeric and not is_measurement:
            center_x = (bbox[0][0] + bbox[2][0]) / 2
            center_y = (bbox[0][1] + bbox[2][1]) / 2
            nx = (center_x / width)  * 20 - 10
            nz = ((center_y / height) * 20 - 10) * aspect
            is_overlap = False
            for r in rooms:
                if ((r["x"] - nx)**2 + (r["z"] - nz)**2)**0.5 < 1.5:
                    is_overlap = True
                    if len(text_clean) > len(r["name"]):
                        r["name"] = text_clean
                    break
            if not is_overlap:
                rooms.append({"name": text_clean, "x": float(nx), "z": float(nz)})
    return rooms


