import sys

file_path = r'C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\app\services\vision\algorithms.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix V5: Remove the expand_tetris definition and working_free injection
tetris_def = '''    def expand_tetris(cx, cy, current_free):
        if cy < 0 or cy >= height or cx < 0 or cx >= width or current_free[cy, cx] == 0:
            return None
        rect = expand_from_point(cx, cy, current_free)
        if not rect: return None
        x1, y1, x2, y2 = rect
        if x2 - x1 < 10 or y2 - y1 < 10: return None
        return rect

    working_free = free.copy()
    min_area = int(height * width * 0.003)
    if len(rooms_raw) > 0:'''

content = content.replace(tetris_def, '    if len(rooms_raw) > 0:', 1)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print('V5 fixed!')
