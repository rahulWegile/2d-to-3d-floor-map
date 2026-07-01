file_path = r'C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\app\services\vision\pipeline.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace import line
content = content.replace(
    'from app.services.vision.algorithms import _expand_rooms_v2, _expand_rooms_v3, _expand_rooms_v4, _expand_rooms_v5, _expand_rooms_v6',
    'from app.services.vision.algorithms import _expand_rooms_v4, _expand_rooms_v5, _expand_rooms_v6'
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed pipeline.py imports')
