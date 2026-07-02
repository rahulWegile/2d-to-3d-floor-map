import os
import json
import base64
import time

def _extract_rooms_gemini(img_bytes, height, width):
    prompt = """
    You are an expert architectural blueprint digitizer. Your task is to segment a 2D floorplan into its distinct interior rooms by drawing bounding boxes.
    
    You must return a JSON array of objects, where each object strictly has:
    - "name": the text label of the room (use "" if unlabeled).
    - "ymin": bounding box top edge (0-1000 scale).
    - "xmin": bounding box left edge (0-1000 scale).
    - "ymax": bounding box bottom edge (0-1000 scale).
    - "xmax": bounding box right edge (0-1000 scale).
    
    CRITICAL RULES FOR DRAWING BOUNDING BOXES:
    You are generating the FINAL coordinates that will be rendered in a 3D engine. You must draw these boxes like perfectly fitting puzzle pieces.
    
    1. STAY INSIDE THE HOUSE (OUTER WALLS):
       - NEVER let a bounding box extend beyond the thick outer exterior walls of the building.
       - If a tile extends into the empty white space outside the blueprint, the system will break.
       
    2. PERFECTLY FLUSH PUZZLE PIECES (NO GAPS):
       - Do NOT leave empty space between adjacent rooms. If a Bedroom is next to a Hallway, the xmax of the Bedroom MUST EXACTLY MATCH the xmin of the Hallway. 
       - Every interior walk-able space must be covered. 
       
    3. STRICTLY NO OVERLAPPING:
       - NO TWO BOUNDING BOXES CAN OVERLAP. They can share an exact edge, but their interior areas must never intersect. If Room A overlaps Room B by even 1 coordinate point, the 3D renderer will glitch.
       
    4. WALL BOUNDARIES:
       - Stop your bounding box exactly at the inner edge of structural walls. Never pass through a structural wall. 
    
    Remember: (0,0) is the top-left corner of the image, and (1000,1000) is the bottom-right. 
    Return ONLY the raw JSON array. Do not include markdown formatting or explanations.
    """
    
    rooms_data = None
    base64_image = base64.b64encode(img_bytes).decode('utf-8')
    
    # 1. ATTEMPT GEMINI FIRST (Primary: Free and Highly Accurate)
    try:
        from google import genai
        from google.genai import types
        
        gemini_keys = [
            os.environ.get("GEMINI_API_KEY_1", ""),
            os.environ.get("GEMINI_API_KEY_2", ""),
            os.environ.get("GEMINI_API_KEY_3", "")
        ]
        
        fallback_models = [
            "gemini-flash-latest",
            "gemini-2.5-flash",
            "gemini-2.0-flash"
        ]
        
        image_part = types.Part.from_bytes(data=img_bytes, mime_type='image/jpeg')
        response = None
        last_err = None
        
        for key in gemini_keys:
            if response: break
            gemini_client = genai.Client(api_key=key)
            
            for model_name in fallback_models:
                try:
                    response = gemini_client.models.generate_content(
                        model=model_name,
                        contents=[prompt, image_part],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                    print(f"Gemini Vision Success on {model_name} using key ending in ...{key[-4:]}!")
                    break
                except Exception as ex:
                    last_err = ex
                    print(f"Gemini API Error on {model_name} with key ...{key[-4:]}, trying next...")
                    time.sleep(1)
                    
        if response:
            rooms_data = json.loads(response.text)
        else:
            raise last_err
            
    except Exception as e:
        print(f"Gemini API Error across all keys/models: {e}, falling back to OpenRouter...")
        
    # 2. FALLBACK TO OPENROUTER (GPT-4o)
    if rooms_data is None:
        try:
            from openai import OpenAI
            or_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            )
            
            chat_completion = or_client.chat.completions.create(
                model="openai/gpt-4o",
                messages=[
                    {
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
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=1500
            )
            
            content = chat_completion.choices[0].message.content
            if content is None:
                raise ValueError("OpenRouter returned None (Likely out of credits).")
                
            txt = content.strip()
            if txt.startswith("```json"): txt = txt[7:]
            if txt.startswith("```"): txt = txt[3:]
            if txt.endswith("```"): txt = txt[:-3]
            
            parsed = json.loads(txt.strip())
            if isinstance(parsed, dict) and len(parsed.keys()) == 1:
                rooms_data = list(parsed.values())[0]
            else:
                rooms_data = parsed
                
            print("OpenRouter (GPT-4o) Success!")
            
        except Exception as e:
            print(f"OpenRouter Fallback Error: {e}")
            
    if not rooms_data or not isinstance(rooms_data, list):
        return []
        
    aspect = height / width
    rooms = []
    for r in rooms_data:
        xmin = r.get("xmin", 0)
        xmax = r.get("xmax", 0)
        ymin = r.get("ymin", 0)
        ymax = r.get("ymax", 0)
        
        # Translate 0-1000 AI coordinates directly to 3D space
        xmin_3d = (xmin / 1000.0) * 20 - 10
        xmax_3d = (xmax / 1000.0) * 20 - 10
        ymin_3d = ((ymin / 1000.0) * 20 - 10) * aspect
        ymax_3d = ((ymax / 1000.0) * 20 - 10) * aspect
        
        # No deflation margin - trust the AI's exact bounding box for flush puzzle pieces
        
        if xmax_3d <= xmin_3d: xmax_3d = xmin_3d + 0.1
        if ymax_3d <= ymin_3d: ymax_3d = ymin_3d + 0.1
        
        orig_x = (xmin_3d + xmax_3d) / 2
        orig_z = (ymin_3d + ymax_3d) / 2
        
        
        rooms.append({
            "name": r.get("name", "Unknown"),
            "x": float(orig_x),
            "z": float(orig_z),
            "w": float(abs(xmax_3d - xmin_3d)),
            "h": float(abs(ymax_3d - ymin_3d)),
            "polygon": [
                {"x": float(xmin_3d), "z": float(ymin_3d)},
                {"x": float(xmax_3d), "z": float(ymin_3d)},
                {"x": float(xmax_3d), "z": float(ymax_3d)},
                {"x": float(xmin_3d), "z": float(ymax_3d)},
            ],
            "box_2d": [xmin, xmax, ymin, ymax]
        })
        
    return rooms