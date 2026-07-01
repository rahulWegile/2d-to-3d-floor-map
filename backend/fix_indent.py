file_path = r'C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\app\services\vision\algorithms.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
in_v4 = False
unindent = False

for line in lines:
    if line.startswith('def _expand_rooms_v4'):
        in_v4 = True
        
    if in_v4 and '# --- NATIVE LABELED LOGIC' in line:
        unindent = True
        new_lines.append(line)
        continue
        
    if in_v4 and unindent:
        if line.startswith('        '):
            new_lines.append(line[4:]) # unindent 4 spaces
        else:
            new_lines.append(line)
            if line.startswith('    return final_rooms'):
                unindent = False
                in_v4 = False
    else:
        new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Fixed indentation in V4!')
