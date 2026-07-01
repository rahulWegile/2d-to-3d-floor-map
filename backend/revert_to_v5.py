file_path = r'C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\app\services\vision\algorithms.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# find v5
start_v5 = content.find('def _expand_rooms_v5')
start_v6 = content.find('def _expand_rooms_v6')
start_v4 = content.find('def _expand_rooms_v4')

if start_v6 == -1:
    v6_end = len(content)
else:
    # v6 ends where v4 begins
    v6_end = start_v4

# extract v5 code
v5_code = content[start_v5:start_v6]

# create v6 code by replacing name
v6_code = v5_code.replace('def _expand_rooms_v5', 'def _expand_rooms_v6')

# construct new content
new_content = content[:start_v6] + v6_code + content[v6_end:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)
print('Reverted V6 to exact clone of V5')
