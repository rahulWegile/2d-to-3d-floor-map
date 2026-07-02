import os
import base64
from openai import OpenAI

# Initialize the client with the provided NVIDIA API key
client = OpenAI(
  base_url="https://integrate.api.nvidia.com/v1",
  api_key=os.getenv("NVIDIA_API_KEY", "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")
)

def extract_rooms_from_image(image_path):
    print(f"Loading image: {image_path}")
    
    # Read and base64 encode the image
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        
    prompt = """
    Look at this floor plan image. Please identify all the rooms and return a structured JSON array.
    For each room, include:
    - 'name': The name of the room (e.g., 'Bedroom 1', 'Kitchen')
    - 'x', 'z': The approximate center coordinates of the room
    - 'w', 'h': The approximate width and height of the room
    
    Only return the JSON array and nothing else.
    """

    print("Sending request to Nemotron-3-Nano-Omni...")
    completion = client.chat.completions.create(
      model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
      messages=[
        {
          "role": "user",
          "content": [
            {"type": "text", "text": prompt},
            {
              "type": "image_url",
              "image_url": {
                "url": f"data:image/png;base64,{encoded_string}"
              }
            }
          ]
        }
      ],
      temperature=0.6,
      top_p=0.95,
      max_tokens=2048,
      stream=False
    )

    print("\n--- Response ---")
    print(completion.choices[0].message.content)

if __name__ == "__main__":
    # Point this to one of your uploaded floor plan images
    image_to_test = r"C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\uploads\floor_img_0_1782970767672.png"
    
    if os.path.exists(image_to_test):
        extract_rooms_from_image(image_to_test)
    else:
        print(f"Image not found at {image_to_test}. Please update the path!")
