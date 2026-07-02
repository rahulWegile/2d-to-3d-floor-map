import os
import base64
import json
import time
from openai import OpenAI

API_KEY = "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"
IMG_PATH = r"C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\image copy 20.png"

MODELS = [
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "qwen/qwen3.5-397b-a17b"
]

prompt = """
Your role: Expert architectural blueprint digitizer.
Your task: Analyze the provided 2D floorplan image and segment EVERY interior space into bounding boxes.

OUTPUT FORMAT:
Return a strictly valid JSON array. Each object must have exactly these keys:
  "name"  — the room label as written on the blueprint (e.g. "Bedroom 1", "Living Room", "Hallway"). Use "Room" if unlabeled.
  "xmin"  — left edge of the box (0–1000).
  "ymin"  — top edge of the box (0–1000).
  "xmax"  — right edge of the box (0–1000).
  "ymax"  — bottom edge of the box (0–1000).

Return ONLY the raw JSON array. No markdown fences, no comments.
"""

def main():
    if not os.path.exists(IMG_PATH):
        print("Image not found:", IMG_PATH)
        return
        
    with open(IMG_PATH, "rb") as f:
        base64_image = base64.b64encode(f.read()).decode('utf-8')
        
    client = OpenAI(
      base_url="https://integrate.api.nvidia.com/v1",
      api_key=API_KEY
    )
    
    results = {}
    
    for model in MODELS:
        print(f"\n--- Testing Model: {model} ---")
        try:
            start_time = time.time()
            completion = client.chat.completions.create(
              model=model,
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
              max_tokens=2048,
              stream=False
            )
            duration = time.time() - start_time
            content = completion.choices[0].message.content
            print(f"Time: {duration:.2f}s")
            
            # Clean formatting
            txt = content.strip()
            if txt.startswith("```json"): txt = txt[7:]
            if txt.startswith("```"): txt = txt[3:]
            if txt.endswith("```"): txt = txt[:-3]
            txt = txt.strip()
            
            try:
                data = json.loads(txt)
                if isinstance(data, list):
                    rooms = len(data)
                    print(f"SUCCESS! Found {rooms} rooms.")
                    results[model] = {"status": "success", "rooms": rooms, "time": duration}
                else:
                    print("FAILED: Returned JSON but not a list.")
                    results[model] = {"status": "bad_format"}
            except json.JSONDecodeError:
                print("FAILED: Did not return valid JSON.")
                print(f"Raw output: {txt[:100]}...")
                results[model] = {"status": "invalid_json"}
                
        except Exception as e:
            print(f"API Error: {e}")
            results[model] = {"status": "api_error", "error": str(e)}
            
    print("\n--- FINAL RESULTS ---")
    for m, r in results.items():
        print(f"{m}: {r}")

if __name__ == '__main__':
    main()
