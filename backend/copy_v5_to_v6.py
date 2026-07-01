import sys

file_path = r'C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\app\services\vision\algorithms.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_v5 = -1
end_v5 = -1
for i, line in enumerate(lines):
    if line.startswith('def _expand_rooms_v5'):
        start_v5 = i
    if line.startswith('def _expand_rooms_v6'):
        end_v5 = i
        break

start_v6 = end_v5
end_v6 = len(lines)

if start_v5 == -1 or end_v5 == -1:
    print('Failed to find indices')
    sys.exit(1)

v5_lines = lines[start_v5:end_v5]
# Replace function name
v5_lines[0] = v5_lines[0].replace('def _expand_rooms_v5', 'def _expand_rooms_v6')
# Replace docstring
for i in range(1, 5):
    if 'v5 pipeline' in v5_lines[i]:
        v5_lines[i] = v5_lines[i].replace('v5 pipeline', 'v6 pipeline (Exact clone of V5)')
# Replace debug paths
for i in range(len(v5_lines)):
    if 'v5_' in v5_lines[i]:
        v5_lines[i] = v5_lines[i].replace('v5_', 'v6_')

new_lines = lines[:start_v6] + v5_lines

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("V6 replaced with exact V5 clone successfully.")
