file_path = r'C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\app\services\vision\algorithms.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

new_return = '''    import json
    with open("uploads/debug/final_rooms_debug.json", "w") as f:
        json.dump(final_rooms, f, indent=2)
    return final_rooms'''

content = content.replace('    return final_rooms', new_return, 1)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Injected debug dump')
