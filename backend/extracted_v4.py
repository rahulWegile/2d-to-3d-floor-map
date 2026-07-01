def _expand_rooms_v4(rooms_raw, wall_mask, wall_thickness, height, width):

4:     """

5:     v4 pipeline:

6:     Updated with v3 improvements (lower core threshold, core-to-label nearest matching, fallback handling)

7:     while keeping the v4 debug logs.

8:     """

9:     from collections import deque, defaultdict

10:     import numpy as np

11:     import cv2

12:     import os

13:     

14:     os.makedirs("uploads/debug", exist_ok=True)

15:     

16:     # 1. Debug Wall Mask

17:     cv2.imwrite("uploads/debug/walls.png", wall_mask)

18:     

19:     aspect = height / width

20:     

21:     def to_px(nx, nz):

22:         px = int((nx + 10) / 20 * width)

23:         py = int((nz / aspect + 10) / 20 * height)

24:         return max(0, min(width - 1, px)), max(0, min(height - 1, py))

25: 

26:     def to_3d(px, py):

27:         return float((px / width) * 20 - 10), float(((py / height) * 20 - 10) * aspect)

28: 

29:     # 1. Wall Extraction -> Free space

30:     free = (wall_mask == 0).astype(np.uint8) * 255

31:     

32:     # 2. Room Extraction -> Distance Transform Cores

33:     dist = cv2.distanceTransform(free, cv2.DIST_L2, 5)

34:     

35:     # Senior Dev Fix: Smooth the distance transform to remove local noise.

36:     dist_smooth = cv2.GaussianBlur(dist, (15, 15), 0)

37:     

38:     # Find local maxima (peaks of rooms)

39:     local_max = cv2.dilate(dist_smooth, np.ones((7,7)))

40:     

41:     # Lower threshold significantly so narrow rooms (Entrance, Balcony) always get cores.

42:     core_threshold = 2

43:     cores = ((dist_smooth == local_max) & (dist_smooth > core_threshold)).astype(np.uint8) * 255

44:     cores = cv2.dilate(cores, np.ones((3,3)))

45:     

46:     # Debug: save cores to verify hallway is connected

47:     cv2.imwrite("uploads/debug/room_cores.png", cores)

48:     

49:     num_labels, comp_map = cv2.connectedComponents(cores)

50:     

51:     # Core BFS to partition free space (Voronoi of cores)

52:     queue = deque()

53:     region_map = np.zeros_like(comp_map, dtype=np.int32)

54:     

55:     ys, xs = np.where(comp_map > 0)

56:     for y, x in zip(ys, xs):

57:         queue.append((x, y, comp_map[y, x]))

58:         region_map[y, x] = comp_map[y, x]

59:         

60:     while queue:

61:         x, y, cid = queue.popleft()

62:         for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:

63:             nx, ny = x + dx, y + dy

64:             if 0 <= nx < width and 0 <= ny < height:

65:                 if free[ny, nx] > 0 and region_map[ny, nx] == 0:

66:                     region_map[ny, nx] = cid

67:                     queue.append((nx, ny, cid))

68:                     

69:     # 3. Label-to-Room Matching

70:     core_to_labels = defaultdict(list)

71:     for idx, room in enumerate(rooms_raw):

72:         sx, sy = to_px(room['x'], room['z'])

73:         cid = region_map[sy, sx]

74:         

75:         if cid == 0:

76:             # OCR label landed on a wall or outside. Radial search for nearest region.

77:             found = 0

78:             for r in range(1, int(min(width, height) * 0.1), 2):

79:                 y_min = max(0, sy - r); y_max = min(height - 1, sy + r)

80:                 x_min = max(0, sx - r); x_max = min(width - 1, sx + r)

81:                 roi = region_map[y_min:y_max+1, x_min:x_max+1]

82:                 if np.any(roi > 0):

83:                     ys_roi, xs_roi = np.where(roi > 0)

84:                     ys_global = ys_roi + y_min; xs_global = xs_roi + x_min

85:                     dists = (xs_global - sx)**2 + (ys_global - sy)**2

86:                     min_idx = np.argmin(dists)

87:                     found = region_map[ys_global[min_idx], xs_global[min_idx]]

88:                     break

89:             cid = found

90:             

91:         if cid > 0:

92:             core_to_labels[cid].append((idx, sx, sy))

93:             

94:     # 4. Region Generation & Open-Plan Sub-partitioning

95:     room_masks = {}

96:     for cid, labels in core_to_labels.items():

97:         core_mask = (region_map == cid)

98:         if len(labels) == 1:

99:             room_masks[labels[0][0]] = core_mask

100:         else:

101:             # Multiple labels in one room (Open Plan!) -> Sub-partition using Voronoi

102:             ys, xs = np.where(core_mask)

103:             pts = np.column_stack((xs, ys)) # (N, 2)

104:             label_pts = np.array([[l[1], l[2]] for l in labels]) # (K, 2)

105:             # dists shape: (N, K)

106:             dists = np.sum((pts[:, None, :] - label_pts[None, :, :])**2, axis=2)

107:             closest_idx = np.argmin(dists, axis=1)

108:             

109:             for i, l in enumerate(labels):

110:                 idx = l[0]

111:                 sub_mask = np.zeros_like(core_mask, dtype=bool)

112:                 sub_mask[ys[closest_idx == i], xs[closest_idx == i]] = True

113:                 room_masks[idx] = sub_mask

114: 

115:     # Helper: 4-way expansion (Frozen as requested)

116:     def expand_from_point(cx, cy):

117:         x1 = x2 = cx

118:         y1 = y2 = cy

119:         fl = fr = ft = fb = False

120:         while not (fl and fr and ft and fb):

121:             ox1, oy1, ox2, oy2 = x1, y1, x2, y2

122:             if not fl:

123:                 if ox1 - 1 >= 0 and free[oy1:oy2 + 1, ox1 - 1].all(): x1 = ox1 - 1

124:                 else: fl = True

125:             if not fr:

126:                 if ox2 + 1 < width and free[oy1:oy2 + 1, ox2 + 1].all(): x2 = ox2 + 1

127:                 else: fr = True

128:             if not ft:

129:                 if oy1 - 1 >= 0 and free[oy1 - 1, ox1:ox2 + 1].all(): y1 = oy1 - 1

130:                 else: ft = True

131:             if not fb:

132:                 if oy2 + 1 < height and free[oy2 + 1, ox1:ox2 + 1].all(): y2 = oy2 + 1

133:                 else: fb = True

134:             if x1 == ox1 and x2 == ox2 and y1 == oy1 and y2 == oy2: break

135:         if x2 - x1 < 4 or y2 - y1 < 4: return None

136:         return x1, y1, x2, y2

137: 

138:     expanded = []

139: 

140:     expanded_dict = {}

141: 

142:     # Sort rooms by name alphabetically (case-insensitive) to determine expansion order preference

143:     sorted_rooms_with_indices = sorted(enumerate(rooms_raw), key=lambda x: x[1]['name'].lower())

144: 

145:     # Debug: Overlay container

146:     for idx, room in sorted_rooms_with_indices:

147:         sx, sy = to_px(room['x'], room['z'])

148:         clean_name = "".join(c for c in room['name'] if c.isalnum())

149:         

150:         has_expanded = False

151:         if idx in room_masks:

152:             mask = room_masks[idx]

153:             if not np.any(mask):

154:                 expanded_dict[idx] = room

155:                 continue

156:             

157:             # Prefer starting at the original label position if it's inside the mask and free

158:             if mask[sy, sx] and free[sy, sx] != 0:

159:                 cx, cy = sx, sy

160:             else:

161:                 # Find centroid of this specific room's region

162:                 M = cv2.moments(mask.astype(np.uint8))

163:                 if M["m00"] != 0:

164:                     cx = int(M["m10"] / M["m00"])

165:                     cy = int(M["m01"] / M["m00"])

166:                 else:

167:                     cx, cy = sx, sy

168:                     

169:                 # If centroid is outside the mask, snap to nearest pixel IN mask

170:                 if not mask[cy, cx]:

171:                     ys, xs = np.where(mask)

172:                     dists = (xs - cx)**2 + (ys - cy)**2

173:                     min_idx = np.argmin(dists)

174:                     cx, cy = xs[min_idx], ys[min_idx]

175:                 

176:             # DEBUG IMAGE: Overlay

177:             debug_img = cv2.cvtColor((mask.astype(np.uint8) * 255), cv2.COLOR_GRAY2BGR)

178:             debug_img[mask] = [0, 255, 0] # Green mask

179:             cv2.circle(debug_img, (cx, cy), 5, (0, 0, 255), -1) # Centroid red

180:             

181:             if 0 <= cx < width and 0 <= cy < height and free[cy, cx] != 0:

182:                 rect = expand_from_point(cx, cy)

183:                 if rect:

184:                     x1, y1, x2, y2 = rect

185:                     

186:                     # Mark the expanded region as occupied in the free mask to prevent overlap

187:                     free[y1:y2+1, x1:x2+1] = 0

188:                     

189:                     x1 += 3; x2 -= 3; y1 += 3; y2 -= 3

190:                     

191:                     # Debug: draw rectangle

192:                     cv2.rectangle(debug_img, (x1, y1), (x2, y2), (255, 0, 0), 2) # Blue rectangle

193:                     

194:                     if x2 - x1 >= 4 and y2 - y1 >= 4:

195:                         rx1, rz1 = to_3d(x1, y1)

196:                         rx2, rz2 = to_3d(x2, y2)

197:                         expanded_dict[idx] = {

198:                             "name": room['name'],

199:                             "x": room['x'], "z": room['z'],

200:                             "w": abs(rx2 - rx1), "h": abs(rz2 - rz1),

201:                             "polygon": [

202:                                 {"x": rx1, "z": rz1}, {"x": rx2, "z": rz1},

203:                                 {"x": rx2, "z": rz2}, {"x": rx1, "z": rz2},

204:                             ],

205:                         }

206:                         cv2.imwrite(f"uploads/debug/room_{clean_name}.png", debug_img)

207:                         has_expanded = True

208:                         

209:             if not has_expanded:

210:                 cv2.imwrite(f"uploads/debug/room_{clean_name}.png", debug_img)

211:                 

212:         if not has_expanded:

213:             expanded_dict[idx] = room

214:             

215:     # Reconstruct the expanded list in the original order of rooms_raw

216:     expanded = [expanded_dict[i] for i in range(len(rooms_raw))]

217:     return expanded

The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.


---NEXT---

Created At: 2026-06-26T11:01:59+05:30
Completed At: 2026-06-26T11:01:59+05:30
The following changes were made by the replace_file_content tool to: C:\Users\Mehak\OneDrive\Desktop\Floor to 3D\floor_to_3d\backend\app\services\vision\algorithms.py. If relevant, proactively run terminal commands to execute this code for the USER. Don't ask for permission.
[diff_block_start]
@@ -1,5 +1,251 @@
 import cv2

 import os

+

+