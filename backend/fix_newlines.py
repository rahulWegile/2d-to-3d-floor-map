file_path = r'C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\app\services\vision\algorithms.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(r'\n    return final_rooms\n\n', '\n    return final_rooms\n\n')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed literal newlines')
