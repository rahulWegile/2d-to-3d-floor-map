import sys

file_path = r'C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\app\services\vision\algorithms.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

v6_start = -1
v6_end = len(lines)
for i, line in enumerate(lines):
    if line.startswith('def _expand_rooms_v6'):
        v6_start = i
        break

if v6_start == -1:
    print('V6 not found')
    sys.exit(1)

# In V6, replace the if len(rooms_raw) > 0: block with the Tetris logic from rewrite_v6.py
with open('rewrite_v6.py', 'r', encoding='utf-8') as f:
    rewrite_content = f.read()

# We know the Tetris logic in rewrite_v6.py starts around if len(rooms_raw) > 0: and ends at lse:
start_tetris = rewrite_content.find('    if len(rooms_raw) > 0:\n        # --- NATIVE LABELED LOGIC (NO V4 CALLS) ---')
end_tetris = rewrite_content.find('    else:\n        # --- NATIVE UNLABELED FALLBACK ---')

if start_tetris == -1 or end_tetris == -1:
    print('Failed to find Tetris logic in rewrite_v6.py')
    sys.exit(1)

tetris_code = rewrite_content[start_tetris:end_tetris]

# Now find where to replace it in algorithms.py
# In algorithms.py, V6 currently has:
#    if len(rooms_raw) > 0:
#        return _expand_rooms_v4(rooms_raw, wall_mask, wall_thickness, height, width)
# We replace this with tetris_code.

v6_lines = ''.join(lines[v6_start:])
old_if_block = '    if len(rooms_raw) > 0:\n        return _expand_rooms_v4(rooms_raw, wall_mask, wall_thickness, height, width)\n'

if old_if_block not in v6_lines:
    print('Could not find the V4 return block in V6')
    sys.exit(1)

new_v6_lines = v6_lines.replace(old_if_block, tetris_code)

new_file_content = ''.join(lines[:v6_start]) + new_v6_lines

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_file_content)

print('Successfully injected Tetris logic into V6!')
