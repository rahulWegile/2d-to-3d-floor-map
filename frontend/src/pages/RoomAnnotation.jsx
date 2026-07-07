import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { fetchSSEForm } from '../api';

const API_BASE = `http://${window.location.hostname}:8081`;

const PALETTE = [
  '#3B82F6','#10B981','#EF4444','#F59E0B',
  '#8B5CF6','#06B6D4','#F97316','#EC4899','#84CC16',
];

const HANDLE_R = 6;

// ── Pure helpers ──────────────────────────────────────────────
function toCanvas3D(x3, z3, cw, ch, aspect) {
  return {
    x: (x3 + 10) / 20 * cw,
    y: (z3 + 10 * aspect) / (20 * aspect) * ch,
  };
}
function to3DCoord(cx, cy, cw, ch, aspect) {
  return { x: (cx / cw) * 20 - 10, z: (cy / ch) * 20 * aspect - 10 * aspect };
}
function wTo3D(wpx, cw)       { return (wpx / cw) * 20; }
function hTo3D(hpx, ch, asp)  { return (hpx / ch) * 20 * asp; }
function wToPx(w3, cw)        { return (w3 / 20) * cw; }
function hToPx(h3, ch, asp)   { return (h3 / (20 * asp)) * ch; }

function polygonCentroid(pts) {
  const n = pts.length;
  return { x: pts.reduce((s, p) => s + p.x, 0) / n, z: pts.reduce((s, p) => s + p.z, 0) / n };
}
function polygonBBox(pts) {
  const xs = pts.map(p => p.x), zs = pts.map(p => p.z);
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minZ: Math.min(...zs), maxZ: Math.max(...zs) };
}
function pointInPolygon(px, py, cpts) {
  let inside = false;
  const n = cpts.length;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = cpts[i].x, yi = cpts[i].y, xj = cpts[j].x, yj = cpts[j].y;
    if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi))
      inside = !inside;
  }
  return inside;
}

// Returns canvas bounding box + canvas polygon points for a room
function getRoomCanvasBBox(room, cw, ch, aspect) {
  if (room.polygon?.length >= 3) {
    const cpts = room.polygon.map(p => toCanvas3D(p.x, p.z, cw, ch, aspect));
    const xs = cpts.map(p => p.x), ys = cpts.map(p => p.y);
    const x1 = Math.min(...xs), y1 = Math.min(...ys), x2 = Math.max(...xs), y2 = Math.max(...ys);
    return { x1, y1, x2, y2, cx: (x1+x2)/2, cy: (y1+y2)/2, cpts };
  }
  const c = toCanvas3D(room.x, room.z, cw, ch, aspect);
  const hw = wToPx(room.w || 2, cw) / 2;
  const hh = hToPx(room.h || 2, ch, aspect) / 2;
  const x1 = c.x - hw, y1 = c.y - hh, x2 = c.x + hw, y2 = c.y + hh;
  return { x1, y1, x2, y2, cx: c.x, cy: c.y,
    cpts: [{x:x1,y:y1},{x:x2,y:y1},{x:x2,y:y2},{x:x1,y:y2}] };
}

function resizeHandles(bbox) {
  return [
    { id:'tl', x:bbox.x1, y:bbox.y1 }, { id:'tr', x:bbox.x2, y:bbox.y1 },
    { id:'bl', x:bbox.x1, y:bbox.y2 }, { id:'br', x:bbox.x2, y:bbox.y2 },
  ];
}

function normalizeRoom(r, i) {
  let x = r.x ?? 0, z = r.z ?? 0, w = r.w, h = r.h;
  if (r.polygon?.length >= 3) {
    const c  = polygonCentroid(r.polygon);
    const bb = polygonBBox(r.polygon);
    x = c.x; z = c.z;
    w = bb.maxX - bb.minX;
    h = bb.maxZ - bb.minZ;
  }
  const defaultName = r.name || `Room ${i + 1}`;
  return { 
    ...r, 
    x, z, w: w || 2, h: h || 2, 
    name: defaultName,
    color: r.color || PALETTE[i % PALETTE.length], 
    _id: r._id ?? i,
    layerNames: r.layerNames || [defaultName, '', ''],
    layerIndex: 1
  };
}

// ── Component ─────────────────────────────────────────────────
export default function RoomAnnotation() {
  const [floors, setFloors]           = useState([]);
  const [activeFloorIdx, setAFI]      = useState(0);
  const [rooms, setRooms]             = useState([]);
  const [selectedIdx, setSelectedIdx] = useState(null);
  const [mode, setMode]               = useState('select');
  const [drawStart, setDrawStart]     = useState(null);
  const [drawCurrent, setDrawCurrent] = useState(null);
  const [drag, setDrag]               = useState(null);
  const [filterMode, setFilterMode]   = useState(false);
  const [editName, setEditName]       = useState('');
  const [editW, setEditW]             = useState('');
  const [editH, setEditH]             = useState('');
  const [projectId, setProjectId]     = useState(null);
  const [projName, setProjName]       = useState('');
  const [loading, setLoading]         = useState(true);
  const [saving, setSaving]           = useState(false);
  const [addingFloor, setAddingFloor] = useState(false);
  const [rotating, setRotating]       = useState(false);
  const [floorToDelete, setFloorToDelete] = useState(null);
  const [alertMessage, setAlertMessage] = useState(null);

  const canvasRef    = useRef(null);
  const imgRef       = useRef(null);
  const addFloorRef  = useRef(null);
  const drawRef      = useRef(null); // always points to latest draw fn
  const location  = useLocation();
  const navigate  = useNavigate();

  const roomsRef = useRef(rooms);
  const floorsRef = useRef(floors);
  const activeFloorIdxRef = useRef(activeFloorIdx);
  const imageCache = useRef({});
  useEffect(() => { roomsRef.current = rooms; }, [rooms]);
  useEffect(() => { floorsRef.current = floors; }, [floors]);
  useEffect(() => { activeFloorIdxRef.current = activeFloorIdx; }, [activeFloorIdx]);

  // ── Load ─────────────────────────────────────────────────────
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const pId = params.get('project_id');
    if (!pId) { navigate('/dashboard'); return; }
    setProjectId(pId);
    const userId = localStorage.getItem('user_id');
    const token  = localStorage.getItem('token');
    fetch(`${API_BASE}/projects/${userId}?t=${Date.now()}`, { headers: { Authorization: 'Bearer ' + token } })
      .then(r => r.json())
      .then(data => {
        const proj = data.projects.find(p => p.project_id === pId);
        if (!proj) { navigate('/dashboard'); return; }
        setProjName(proj.name);
        const raw = proj.rawBackendData || [];
        setFloors(raw);
        setRooms((raw[0]?.rooms || []).map(normalizeRoom));
        setLoading(false);
      })
      .catch(() => navigate('/dashboard'));
  }, []);

  useEffect(() => {
    if (floors[activeFloorIdx]) {
      setRooms((floors[activeFloorIdx].rooms || []).map(normalizeRoom));
      setSelectedIdx(null);
      setMode('select');
      setDrag(null);
      setDrawStart(null);
      setDrawCurrent(null);
    }
  }, [activeFloorIdx, floors]);

  const activeFloor = floors[activeFloorIdx];
  const aspect = activeFloor ? ((activeFloor.height / activeFloor.width) || 0.75) : 0.75;

  // ── Drawing ───────────────────────────────────────────────────
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !activeFloor) return;
    const ctx = canvas.getContext('2d');
    const cw = canvas.width, ch = canvas.height;
    ctx.clearRect(0, 0, cw, ch);
    ctx.fillStyle = '#F8F7F4';
    ctx.fillRect(0, 0, cw, ch);

    if (imgRef.current?.complete && imgRef.current.naturalWidth > 0) {
      ctx.globalAlpha = 0.6;
      ctx.drawImage(imgRef.current, 0, 0, cw, ch);
      ctx.globalAlpha = 1;
    }

    rooms.forEach((room, idx) => {
      if (filterMode && selectedIdx !== null && idx !== selectedIdx) return;
      drawRoom(ctx, room, idx, idx === selectedIdx, cw, ch);
    });

    if (mode === 'draw' && drawStart && drawCurrent) {
      const x = Math.min(drawStart.x, drawCurrent.x), y = Math.min(drawStart.y, drawCurrent.y);
      const w = Math.abs(drawCurrent.x - drawStart.x), h = Math.abs(drawCurrent.y - drawStart.y);
      ctx.globalAlpha = 0.35; ctx.fillStyle = '#2D5F8C'; ctx.fillRect(x, y, w, h);
      ctx.globalAlpha = 1; ctx.strokeStyle = '#2D5F8C'; ctx.lineWidth = 2;
      ctx.setLineDash([5, 4]); ctx.strokeRect(x, y, w, h); ctx.setLineDash([]);
    }
  }, [rooms, selectedIdx, mode, drawStart, drawCurrent, activeFloor, aspect, filterMode]);

  function drawRoom(ctx, room, idx, isSel, cw, ch) {
    const color = room.color || PALETTE[idx % PALETTE.length];
    const bbox  = getRoomCanvasBBox(room, cw, ch, aspect);
    const hasPoly = room.polygon?.length >= 3;

    const pathFn = () => {
      ctx.beginPath();
      bbox.cpts.forEach((p, i) => i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y));
      ctx.closePath();
    };

    // Fill
    ctx.globalAlpha = isSel ? 0.55 : 0.38;
    ctx.fillStyle = color;
    if (hasPoly) { pathFn(); ctx.fill(); }
    else ctx.fillRect(bbox.x1, bbox.y1, bbox.x2 - bbox.x1, bbox.y2 - bbox.y1);

    // Stroke
    ctx.globalAlpha = 1;
    ctx.strokeStyle = isSel ? color : color + 'BB';
    ctx.lineWidth   = isSel ? 2.5 : 1.5;
    if (hasPoly) { pathFn(); ctx.stroke(); }
    else ctx.strokeRect(bbox.x1, bbox.y1, bbox.x2 - bbox.x1, bbox.y2 - bbox.y1);

    // Label
    const label = room.name || '(unnamed)';
    ctx.font = `${isSel ? '700' : '600'} 12px Inter,sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const m = ctx.measureText(label);
    ctx.globalAlpha = 0.92; ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.beginPath();
    ctx.roundRect(bbox.cx - m.width/2 - 5, bbox.cy - 10, m.width + 10, 20, 4);
    ctx.fill();
    ctx.globalAlpha = 1; ctx.fillStyle = '#1A1A1A';
    ctx.fillText(label, bbox.cx, bbox.cy);

    // Resize handles on selected
    if (isSel) {
      resizeHandles(bbox).forEach(h => {
        ctx.fillStyle = '#fff'; ctx.strokeStyle = color; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(h.x, h.y, HANDLE_R, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      });
    }
    ctx.globalAlpha = 1;
  }

  // Keep drawRef current so async callbacks always call the latest version
  useEffect(() => { drawRef.current = draw; }, [draw]);
  useEffect(() => { draw(); }, [draw]);

  // Blueprint image load
  useEffect(() => {
    if (!activeFloor?.imageUrl) return;
    let isActive = true;
    const url = activeFloor.imageUrl.startsWith('/') ? API_BASE + activeFloor.imageUrl : activeFloor.imageUrl;
    
    if (imageCache.current[url]) {
      imgRef.current = imageCache.current[url];
      drawRef.current?.();
      return;
    }

    imgRef.current = null;
    drawRef.current?.();

    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => { 
      imageCache.current[url] = img;
      if (isActive) {
        imgRef.current = img; 
        drawRef.current?.(); 
      }
    };
    img.onerror = () => { 
      if (isActive) {
        imgRef.current = null; 
        drawRef.current?.(); 
      }
    };
    img.src = url;

    return () => { isActive = false; };
  }, [activeFloor?.imageUrl]);

  // ── Mouse interaction ─────────────────────────────────────────
  function getPos(e) {
    const rect = canvasRef.current.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) * (canvasRef.current.width  / rect.width),
      y: (e.clientY - rect.top)  * (canvasRef.current.height / rect.height),
    };
  }

  function findRoomAt(pos) {
    const cw = canvasRef.current.width, ch = canvasRef.current.height;
    for (let i = rooms.length - 1; i >= 0; i--) {
      const { cpts } = getRoomCanvasBBox(rooms[i], cw, ch, aspect);
      if (pointInPolygon(pos.x, pos.y, cpts)) return i;
    }
    return null;
  }

  function findHandle(pos, roomIdx) {
    if (roomIdx === null) return null;
    const cw = canvasRef.current.width, ch = canvasRef.current.height;
    const bbox = getRoomCanvasBBox(rooms[roomIdx], cw, ch, aspect);
    for (const h of resizeHandles(bbox)) {
      if (Math.hypot(pos.x - h.x, pos.y - h.y) <= HANDLE_R + 3) return h.id;
    }
    return null;
  }

  const clonePolygon = r => r.polygon ? r.polygon.map(p => ({ ...p })) : null;

  const handleMouseDown = (e) => {
    if (e.button !== 0) return;
    const pos = getPos(e);
    if (mode === 'draw') { setDrawStart(pos); setDrawCurrent(pos); return; }

    const corner = findHandle(pos, selectedIdx);
    if (corner) {
      const orig = { ...rooms[selectedIdx], polygon: clonePolygon(rooms[selectedIdx]) };
      setDrag({ type:'resize', corner, startPos:pos, origRoom: orig });
      return;
    }

    const idx = findRoomAt(pos);
    if (idx !== null) {
      const r = rooms[idx];
      setSelectedIdx(idx);
      setEditName(r.name || ''); setEditW((r.w||2).toFixed(1)); setEditH((r.h||2).toFixed(1));
      setDrag({ 
        type:'move', 
        startPos:pos, 
        origRoom:{ ...r, polygon: clonePolygon(r) },
        origRooms: rooms.map(room => ({ ...room, polygon: clonePolygon(room) }))
      });
    } else {
      setSelectedIdx(null); setDrag(null);
    }
  };

  const handleMouseMove = (e) => {
    const pos = getPos(e);
    const cw  = canvasRef.current.width, ch = canvasRef.current.height;
    if (mode === 'draw' && drawStart) { setDrawCurrent(pos); return; }
    if (!drag) return;

    const dx = pos.x - drag.startPos.x, dy = pos.y - drag.startPos.y;

    if (drag.type === 'move') {
      const dx3 = wTo3D(dx, cw), dz3 = hTo3D(dy, ch, aspect);
      setRooms(prev => prev.map((r, i) => {
        if (i !== selectedIdx) return r;
        const updated = { ...r, x: drag.origRoom.x + dx3, z: drag.origRoom.z + dz3 };
        if (drag.origRoom.polygon)
          updated.polygon = drag.origRoom.polygon.map(p => ({ x: p.x + dx3, z: p.z + dz3 }));
        return updated;
      }));
    }

    if (drag.type === 'resize') {
      const orig = drag.origRoom;
      const ob   = getRoomCanvasBBox(orig, cw, ch, aspect);
      const c    = drag.corner;
      let x1 = ob.x1, y1 = ob.y1, x2 = ob.x2, y2 = ob.y2;
      if (c.includes('l')) x1 = Math.min(pos.x, ob.x2 - 10);
      if (c.includes('r')) x2 = Math.max(pos.x, ob.x1 + 10);
      if (c.includes('t')) y1 = Math.min(pos.y, ob.y2 - 10);
      if (c.includes('b')) y2 = Math.max(pos.y, ob.y1 + 10);
      const nc  = to3DCoord((x1+x2)/2, (y1+y2)/2, cw, ch, aspect);
      const nw3 = wTo3D(x2 - x1, cw), nh3 = hTo3D(y2 - y1, ch, aspect);
      setRooms(prev => prev.map((r, i) => {
        if (i !== selectedIdx) return r;
        const updated = { ...r, x: nc.x, z: nc.z, w: nw3, h: nh3 };
        if (orig.polygon) {
          const sx = nw3 / (orig.w || 1), sz = nh3 / (orig.h || 1);
          updated.polygon = orig.polygon.map(p => ({
            x: nc.x + (p.x - orig.x) * sx, z: nc.z + (p.z - orig.z) * sz,
          }));
        }
        return updated;
      }));
      setEditW(nw3.toFixed(1)); setEditH(nh3.toFixed(1));
    }
  };

  const handleMouseUp = () => {
    if (mode === 'draw' && drawStart && drawCurrent) {
      const cw = canvasRef.current.width, ch = canvasRef.current.height;
      const x1 = Math.min(drawStart.x, drawCurrent.x), y1 = Math.min(drawStart.y, drawCurrent.y);
      const x2 = Math.max(drawStart.x, drawCurrent.x), y2 = Math.max(drawStart.y, drawCurrent.y);
      if (x2 - x1 > 10 && y2 - y1 > 10) {
        const cx3 = to3DCoord((x1+x2)/2, (y1+y2)/2, cw, ch, aspect);
        const w3  = wTo3D(x2-x1, cw), h3 = hTo3D(y2-y1, ch, aspect);
        const tl  = to3DCoord(x1,y1,cw,ch,aspect), tr = to3DCoord(x2,y1,cw,ch,aspect);
        const br  = to3DCoord(x2,y2,cw,ch,aspect), bl = to3DCoord(x1,y2,cw,ch,aspect);
        const newRoom = { x:cx3.x, z:cx3.z, w:w3, h:h3, name:'New Room',
          polygon:[tl,tr,br,bl], color:PALETTE[rooms.length%PALETTE.length], _id:Date.now() };
        const updated = [...rooms, newRoom];
        setRooms(updated); setSelectedIdx(updated.length-1);
        setEditName('New Room'); setEditW(w3.toFixed(1)); setEditH(h3.toFixed(1));
      }
      setDrawStart(null); setDrawCurrent(null); setMode('select');
      return;
    }
    
    // Apply movement delta to vertically stacked tiles on other floors
    if (drag && drag.type === 'move' && selectedIdx !== null) {
      const latestRoom = roomsRef.current[selectedIdx];
      if (latestRoom) {
        const dx3 = latestRoom.x - drag.origRoom.x;
        const dz3 = latestRoom.z - drag.origRoom.z;
        if (Math.abs(dx3) > 0.001 || Math.abs(dz3) > 0.001) {
          setFloors(prev => prev.map((f, fIdx) => {
            if (fIdx === activeFloorIdxRef.current) return { ...f, rooms: roomsRef.current.map(({ _id, ...r }) => r) };
            return {
              ...f,
              rooms: (f.rooms || []).map((r, rIdx) => {
                if (rIdx !== selectedIdx) return r;
                const updated = { ...r, x: r.x + dx3, z: r.z + dz3 };
                if (r.polygon) {
                  updated.polygon = r.polygon.map(p => ({ x: p.x + dx3, z: p.z + dz3 }));
                }
                return updated;
              })
            };
          }));
        }
      }
    }
    
    setDrag(null);
  };

  // ── Edits ─────────────────────────────────────────────────────
  const setName = (name) => {
    setEditName(name);
    if (selectedIdx === null) return;
    setRooms(prev => prev.map((r, i) => {
      if (i !== selectedIdx) return r;
      const newNames = [...(r.layerNames || [r.name || '', '', ''])];
      newNames[0] = name;
      return { ...r, name, layerNames: newNames };
    }));
  };

  const setLayerName = (roomIdx, layerIdx, value) => {
    setRooms(prev => prev.map((r, i) => {
      if (i !== roomIdx) return r;
      const newNames = [...(r.layerNames || [r.name || '', '', ''])];
      newNames[layerIdx] = value;
      const updated = { ...r, layerNames: newNames };
      
      if (updated.layers && updated.layers.length > layerIdx) {
        updated.layers = [...updated.layers];
        updated.layers[layerIdx] = { ...updated.layers[layerIdx], name: value };
      }
      
      if (layerIdx === 0) {
        updated.name = value;
        if (roomIdx === selectedIdx) setEditName(value);
      }
      return updated;
    }));
  };
  const setColor = (color) => {
    if (selectedIdx === null) return;
    setRooms(prev => prev.map((r, i) => i === selectedIdx ? { ...r, color } : r));
  };
  const applySize = () => {
    const w = parseFloat(editW), h = parseFloat(editH);
    if (!w || !h || selectedIdx === null) return;
    setRooms(prev => prev.map((r, i) => {
      if (i !== selectedIdx) return r;
      const updated = { ...r, w, h };
      if (r.polygon) {
        const sx = w / (r.w||1), sz = h / (r.h||1);
        updated.polygon = r.polygon.map(p => ({ x: r.x+(p.x-r.x)*sx, z: r.z+(p.z-r.z)*sz }));
      }
      return updated;
    }));
  };
  const deleteRoom = () => {
    if (selectedIdx === null) return;
    setRooms(prev => prev.filter((_, i) => i !== selectedIdx));
    setSelectedIdx(null);
  };

  // ── Switch floor (saves current edits before switching) ──────
  const switchFloor = useCallback((newIdx) => {
    if (newIdx === activeFloorIdx) return;
    // Persist current floor's room edits into floors state before switching
    setFloors(prev => prev.map((f, i) =>
      i === activeFloorIdx ? { ...f, rooms: rooms.map(({ _id, ...r }) => r) } : f
    ));
    setAFI(newIdx);
  }, [activeFloorIdx, rooms]);

  // ── Add floor ────────────────────────────────────────────────
  const addFloor = async (file) => {
    if (!file) return;
    setAddingFloor(true);
    try {
      const token = localStorage.getItem('token');
      const userId = localStorage.getItem('user_id');
      const formData = new FormData();
      formData.append('files', file);
      const data = await fetchSSEForm('/upload', formData, (pct, msg) => {
        // Optional: Update progress state if you have one
      });
      if (!data) throw new Error('Invalid response from upload stream');
      const currentFloorsWithEdits = floorsRef.current.map((f, i) =>
        i === activeFloorIdxRef.current ? { ...f, rooms: roomsRef.current.map(({ _id, ...r }) => r) } : f
      );
      const newFloors = [...currentFloorsWithEdits, ...(data.floors || [])];
      await fetch(`${API_BASE}/projects/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
        body: JSON.stringify({ user_id: userId, project_id: projectId, name: projName, rawBackendData: newFloors }),
      });
      setFloors(newFloors);
      setAFI(newFloors.length - 1);
    } catch (err) {
      alert('Failed to add floor: ' + err.message);
    } finally {
      setAddingFloor(false);
      if (addFloorRef.current) addFloorRef.current.value = '';
    }
  };

  // ── Delete floor triggers ──────────────────────────────────────
  const deleteFloor = (idx) => {
    if (floors.length <= 1) {
      setAlertMessage('Cannot delete the only floor in the project.');
      return;
    }
    setFloorToDelete(idx);
  };

  const confirmDeleteFloor = async () => {
    if (floorToDelete === null) return;
    const idx = floorToDelete;
    setFloorToDelete(null);
    setSaving(true);
    try {
      const updatedFloors = floors.filter((_, i) => i !== idx);
      const newIdx = Math.min(activeFloorIdx, updatedFloors.length - 1);
      const userId = localStorage.getItem('user_id');
      const token  = localStorage.getItem('token');
      await fetch(`${API_BASE}/projects/save`, {
        method:'POST',
        headers:{ 'Content-Type':'application/json', Authorization:'Bearer '+token },
        body: JSON.stringify({ user_id:userId, project_id:projectId, name:projName, rawBackendData:updatedFloors }),
      });
      setFloors(updatedFloors);
      setAFI(newIdx);
    } catch (e) {
      setAlertMessage('Failed to delete floor: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  // ── Rotate current floor image 90° clockwise ─────────────────
  // All math is client-side; only the final image file is uploaded (no vision re-run).
  // Coordinate transform for 90° CW: (x, z) → (z/asp, -x/asp)
  // where asp = original H/W (the old aspect ratio).
  const rotateFloor = async () => {
    if (!activeFloor?.imageUrl || rotating) return;
    setRotating(true);
    try {
      const url = activeFloor.imageUrl.startsWith('/')
        ? API_BASE + activeFloor.imageUrl
        : activeFloor.imageUrl;

      const img = await new Promise((resolve, reject) => {
        const im = new Image();
        im.crossOrigin = 'anonymous';
        im.onload = () => resolve(im);
        im.onerror = reject;
        im.src = url;
      });

      const W = img.naturalWidth, H = img.naturalHeight;
      const asp = H / W;

      // Rotate image 90° CW on an offscreen canvas
      const offscreen = document.createElement('canvas');
      offscreen.width  = H;  // new width = old height
      offscreen.height = W;  // new height = old width
      const ctx = offscreen.getContext('2d');
      ctx.translate(H / 2, W / 2);
      ctx.rotate(Math.PI / 2);
      ctx.drawImage(img, -W / 2, -H / 2);

      const rotatedBlob = await new Promise(resolve => offscreen.toBlob(resolve, 'image/png'));

      // Upload image only (no vision processing) to get a permanent URL
      const token = localStorage.getItem('token');
      const fd = new FormData();
      fd.append('file', new File([rotatedBlob], 'rotated.png', { type: 'image/png' }));
      const res = await fetch(`${API_BASE}/upload/save-image`, {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + token },
        body: fd,
      });
      if (!res.ok) throw new Error('Image save failed');
      const { imageUrl: newImageUrl } = await res.json();

      // Transform room coordinates: 90° CW maps pixel (cx,cy)→(H-cy, cx),
      // which in 3D coords gives (x,z) → (-z/asp, x/asp)
      const tp = (x, z) => ({ x: -z / asp, z: x / asp });
      const transformedRooms = rooms.map(room => {
        const nc = tp(room.x, room.z);
        return {
          ...room,
          x: nc.x,
          z: nc.z,
          w: room.h / asp,
          h: room.w / asp,
          polygon: room.polygon ? room.polygon.map(p => tp(p.x, p.z)) : undefined,
        };
      });

      // Transform wall segments — walls are stored as {points:[{x,z},{x,z}]}
      const transformedWalls = (activeFloor.walls || []).map(wall => {
        let x1, y1, x2, y2;
        if (wall.points && wall.points.length === 2) {
          x1 = wall.points[0].x; y1 = wall.points[0].z;
          x2 = wall.points[1].x; y2 = wall.points[1].z;
        } else {
          x1 = wall.x1 ?? 0; y1 = wall.y1 ?? 0;
          x2 = wall.x2 ?? 0; y2 = wall.y2 ?? 0;
        }
        const p1 = tp(x1, y1);
        const p2 = tp(x2, y2);
        return { points: [{ x: p1.x, z: p1.z }, { x: p2.x, z: p2.z }] };
      });

      imageCache.current = {};

      const updatedFloor = {
        ...activeFloor,
        imageUrl: newImageUrl,
        width:  H,  // swapped
        height: W,  // swapped
        rooms: transformedRooms.map(({ _id, ...r }) => r),
        walls: transformedWalls,
      };
      const updatedFloors = floors.map((f, i) => i === activeFloorIdx ? updatedFloor : f);

      const userId = localStorage.getItem('user_id');
      await fetch(`${API_BASE}/projects/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
        body: JSON.stringify({ user_id: userId, project_id: projectId, name: projName, rawBackendData: updatedFloors }),
      });

      setFloors(updatedFloors);
    } catch (err) {
      alert('Failed to rotate: ' + err.message);
    } finally {
      setRotating(false);
    }
  };

  // ── Build ─────────────────────────────────────────────────────
  const handleBuild = async () => {
    setSaving(true);
    const updatedFloors = floors.map((f, i) => {
      if (i !== activeFloorIdx) return f;
      return { ...f, rooms: rooms.map(({ _id, ...r }) => r) };
    });
    const userId = localStorage.getItem('user_id');
    const token  = localStorage.getItem('token');
    
    try {
      const res = await fetch(`${API_BASE}/projects/save`, {
        method:'POST',
        headers:{ 'Content-Type':'application/json', Authorization:'Bearer '+token },
        body: JSON.stringify({ user_id:userId, project_id:projectId, name:projName, rawBackendData:updatedFloors }),
      });
      if (!res.ok) {
        const txt = await res.text();
        alert('Save failed: ' + txt);
        setSaving(false);
        return;
      }
      navigate(`/editor?project_id=${projectId}`);
    } catch(e) {
      console.error(e);
      alert('Save error: ' + e.message);
      setSaving(false);
    }
  };

  const handleBack = async () => {
    setSaving(true);
    const updatedFloors = floors.map((f, i) => {
      if (i !== activeFloorIdx) return f;
      return { ...f, rooms: rooms.map(({ _id, ...r }) => r) };
    });
    const userId = localStorage.getItem('user_id');
    const token  = localStorage.getItem('token');
    try {
      await fetch(`${API_BASE}/projects/save`, {
        method:'POST',
        headers:{ 'Content-Type':'application/json', Authorization:'Bearer '+token },
        body: JSON.stringify({ user_id:userId, project_id:projectId, name:projName, rawBackendData:updatedFloors }),
      });
    } catch(e) {
      console.error("Failed to auto-save on back", e);
    }
    navigate('/dashboard');
  };

  if (loading) return (
    <div style={{ width:'100vw', height:'100vh', display:'flex', alignItems:'center', justifyContent:'center', background:'#faf9f7', fontFamily:"'Inter',sans-serif", fontSize:15 }}>
      Loading floor plan…
    </div>
  );

  const selected = selectedIdx !== null ? rooms[selectedIdx] : null;

  // ── UI ────────────────────────────────────────────────────────
  return (
    <div style={{ width:'100vw', height:'100vh', display:'flex', flexDirection:'column', background:'#faf9f7', fontFamily:"'Inter',sans-serif", overflow:'hidden' }}>

      {/* Header */}
      <div style={{ height:54, background:'#fff', borderBottom:'1px solid #EBEBEB', display:'flex', alignItems:'center', padding:'0 20px', gap:14, flexShrink:0, boxShadow:'0 1px 3px rgba(0,0,0,0.04)' }}>
        <button onClick={handleBack} style={{ background:'transparent', border:'1px solid #EBEBEB', color:'#6B7280', cursor:'pointer', display:'flex', alignItems:'center', gap:6, fontSize:13, fontWeight:500, padding:'5px 12px', borderRadius:7 }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          Back
        </button>
        <div style={{ width:1, height:20, background:'#EBEBEB' }} />
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <div style={{ width:28, height:28, borderRadius:7, background:'#2D5F8C', display:'flex', alignItems:'center', justifyContent:'center' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
          </div>
          <span style={{ color:'#1A1A1A', fontWeight:700, fontSize:14 }}>{projName}</span>
          <span style={{ color:'#9CA3AF', fontSize:13 }}>/ Room Setup</span>
        </div>
        <div style={{ flex:1 }} />

        {/* Hidden file input for adding a floor */}
        <input
          ref={addFloorRef}
          type="file"
          accept="image/png,image/jpeg,application/pdf"
          style={{ display:'none' }}
          onChange={e => { addFloor(e.target.files[0]); }}
        />

        {floors.map((_, i) => (
          <div key={i} style={{ display:'flex', alignItems:'center', gap:0 }}>
            <button onClick={() => switchFloor(i)} style={{
              padding:'5px 12px', borderRadius: floors.length > 1 ? '7px 0 0 7px' : 7,
              border:'1px solid', borderRight: floors.length > 1 ? 'none' : undefined,
              borderColor: i === activeFloorIdx ? '#2D5F8C' : '#EBEBEB',
              background: i === activeFloorIdx ? '#F1F5F9' : '#fff',
              color: i === activeFloorIdx ? '#2D5F8C' : '#6B7280',
              fontSize:13, cursor:'pointer', fontWeight: i === activeFloorIdx ? 700 : 500,
            }}>Floor {i+1}</button>
            {floors.length > 1 && (
              <button onClick={() => deleteFloor(i)} title="Delete this floor" style={{
                padding:'5px 7px', borderRadius:'0 7px 7px 0',
                border:'1px solid',
                borderColor: i === activeFloorIdx ? '#2D5F8C' : '#EBEBEB',
                background: i === activeFloorIdx ? '#F1F5F9' : '#fff',
                color:'#9CA3AF', cursor:'pointer', fontSize:13, lineHeight:1,
              }}>×</button>
            )}
          </div>
        ))}

        {/* Add floor button */}
        <button
          onClick={() => addFloorRef.current?.click()}
          disabled={addingFloor}
          title="Upload a new floor blueprint"
          style={{
            display:'flex', alignItems:'center', gap:5,
            padding:'5px 12px', borderRadius:7,
            border:'1px solid #EBEBEB', background:'#fff',
            color:'#6B7280', fontSize:13, fontWeight:500, cursor:'pointer',
            opacity: addingFloor ? 0.6 : 1,
          }}
        >
          {addingFloor
            ? <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{animation:'spin 1s linear infinite'}}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
            : <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          }
          {addingFloor ? 'Processing…' : 'Add Floor'}
        </button>

        {/* Rotate floor button */}
        <button
          onClick={rotateFloor}
          disabled={rotating || !activeFloor?.imageUrl}
          title="Rotate floor plan 90° clockwise"
          style={{
            display:'flex', alignItems:'center', gap:5,
            padding:'5px 12px', borderRadius:7,
            border:'1px solid #EBEBEB', background:'#fff',
            color:'#6B7280', fontSize:13, fontWeight:500, cursor:'pointer',
            opacity: (rotating || !activeFloor?.imageUrl) ? 0.5 : 1,
          }}
        >
          {rotating
            ? <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{animation:'spin 1s linear infinite'}}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
            : <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
          }
          {rotating ? 'Rotating…' : 'Rotate 90°'}
        </button>

        <div style={{ display:'flex', background:'#F5F5F4', borderRadius:8, padding:3, gap:2 }}>
          {['select','draw'].map(m => (
            <button key={m} onClick={() => { setMode(m); setDrawStart(null); setDrawCurrent(null); }} style={{
              padding:'5px 14px', borderRadius:6, border:'none',
              background: mode === m ? '#fff' : 'transparent',
              color: mode === m ? '#1A1A1A' : '#6B7280',
              fontSize:13, fontWeight: mode === m ? 600 : 400, cursor:'pointer',
              boxShadow: mode === m ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
            }}>
              {m === 'select' ? 'Select' : '+ Add Room'}
            </button>
          ))}
        </div>

        <button onClick={handleBuild} disabled={saving} style={{
          padding:'0 20px', height:36, background:'#2D5F8C', color:'#fff',
          border:'none', borderRadius:8, fontWeight:700, fontSize:13, cursor:'pointer',
          display:'flex', alignItems:'center', gap:8, opacity: saving ? 0.7 : 1,
          boxShadow:'0 2px 8px rgba(45,95,140,0.3)',
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M5 3h14l2 5H3z"/><rect x="3" y="8" width="18" height="13" rx="1"/><path d="M9 21v-6h6v6"/></svg>
          {saving ? 'Building…' : 'Build 3D Model'}
        </button>
      </div>

      {/* Body */}
      <div style={{ flex:1, display:'flex', overflow:'hidden' }}>

        {/* Left: room list */}
        <div style={{ width:220, background:'#fff', borderRight:'1px solid #EBEBEB', display:'flex', flexDirection:'column', overflow:'hidden' }}>
          <div style={{ padding:'14px 14px 10px', borderBottom:'1px solid #EBEBEB', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
            <div style={{ fontSize:11, fontWeight:700, color:'#9CA3AF', letterSpacing:'0.08em', textTransform:'uppercase' }}>Rooms ({rooms.length})</div>
            <label style={{ fontSize:11, color:'#6B7280', display:'flex', alignItems:'center', gap:4, cursor:'pointer', fontWeight:600 }}>
              <input type="checkbox" checked={filterMode} onChange={(e) => setFilterMode(e.target.checked)} />
              Isolate Selected
            </label>
          </div>
          <div style={{ flex:1, overflowY:'auto', padding:'8px' }}>
            {rooms.length === 0 && (
              <div style={{ color:'#9CA3AF', fontSize:13, textAlign:'center', padding:'24px 0', lineHeight:1.6 }}>No rooms detected.<br/>Use "Add Room" to draw.</div>
            )}
            {rooms.map((room, idx) => (
              <div key={room._id ?? idx} style={{ marginBottom:4 }}>
                <div
                  onClick={() => { setSelectedIdx(idx); setEditName(room.name||''); setEditW((room.w||2).toFixed(1)); setEditH((room.h||2).toFixed(1)); }}
                  style={{
                    padding:'8px 10px', borderRadius: idx === selectedIdx ? '8px 8px 0 0' : 8, cursor:'pointer',
                    display:'flex', alignItems:'center', gap:9,
                    background: idx === selectedIdx ? '#F1F5F9' : 'transparent',
                    border: `1px solid ${idx === selectedIdx ? '#CBD5E1' : 'transparent'}`,
                    borderBottom: idx === selectedIdx ? 'none' : undefined,
                  }}>
                  <div style={{ width:11, height:11, borderRadius:3, background:room.color, flexShrink:0 }} />
                  <span style={{ color: idx === selectedIdx ? '#2D5F8C' : '#4B5563', fontSize:13, fontWeight: idx === selectedIdx ? 600 : 400, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                    {room.name || '(unnamed)'}
                  </span>
                </div>
                
                {idx === selectedIdx && (() => {
                  const getUniqueLayerNames = (lIdx) => {
                      const names = new Set();
                      
                      // 1. Get from all other floors in the floors array
                      floors.forEach((f, i) => {
                          if (i === activeFloorIdx) return; // Skip current floor in the floors array since it's stale
                          (f.rooms||[]).forEach(r => {
                              const n = lIdx === 0 ? (r.layerNames?.[0] || r.name) : r.layerNames?.[lIdx];
                              if (n && n.trim() && !/^Room \d+$/i.test(n.trim())) names.add(n.trim());
                          });
                      });
                      
                      // 2. Get from the current floor using the live 'rooms' state
                      rooms.forEach(r => {
                          const n = lIdx === 0 ? (r.layerNames?.[0] || r.name) : r.layerNames?.[lIdx];
                          if (n && n.trim() && !/^Room \d+$/i.test(n.trim())) names.add(n.trim());
                      });

                      return Array.from(names).sort();
                  };

                  const renderInput = (lIdx, label) => {
                      const currentVal = lIdx === 0 ? (room.layerNames?.[0] ?? room.name ?? '') : (room.layerNames?.[lIdx] ?? '');
                      const presets = getUniqueLayerNames(lIdx).filter(n => n !== currentVal);
                      return (
                          <div>
                            <div style={{ fontSize: 10, color: '#475569', fontWeight: 700, marginBottom: 4, letterSpacing: '0.05em' }}>{label}</div>
                            <input value={currentVal} onChange={(e) => setLayerName(idx, lIdx, e.target.value)} placeholder="e.g. Zone" style={{ width: '100%', padding: '6px 8px', borderRadius: 4, border: '1px solid #CBD5E1', fontSize: 12, outline: 'none', boxSizing: 'border-box' }} />
                            {presets.length > 0 && (
                                <div style={{ display:'flex', flexWrap:'wrap', gap:5, marginTop:6, maxHeight:'65px', overflowY:'auto', paddingRight:2, alignContent:'flex-start' }} className="custom-scrollbar-mini">
                                    {presets.map(n => (
                                        <div key={n} onClick={() => setLayerName(idx, lIdx, n)} 
                                             style={{ fontSize:10, background:'#F1F5F9', border:'1px solid #CBD5E1', color:'#475569', padding:'3px 8px', borderRadius:12, cursor:'pointer', fontWeight:500 }}
                                             onMouseOver={(e) => { e.currentTarget.style.background = '#2D5F8C'; e.currentTarget.style.color = '#fff'; }}
                                             onMouseOut={(e) => { e.currentTarget.style.background = '#F1F5F9'; e.currentTarget.style.color = '#475569'; }}>
                                            {n}
                                        </div>
                                    ))}
                                </div>
                            )}
                          </div>
                      );
                  };

                  return (
                      <div style={{ padding: '12px 14px', background: '#F1F5F9', borderRadius: '0 0 8px 8px', border: '1px solid #CBD5E1', borderTop: 'none', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {renderInput(0, 'LAYER 1 (BASE)')}
                        {renderInput(1, 'LAYER 2 (MIDDLE)')}
                        {renderInput(2, 'LAYER 3 (TOP)')}
                      </div>
                  );
                })()}
              </div>
            ))}
          </div>
        </div>

        {/* Canvas */}
        <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', background:'#F0EEE9', position:'relative', overflow:'hidden' }}>
          {mode === 'draw' && (
            <div style={{ position:'absolute', top:14, left:'50%', transform:'translateX(-50%)', background:'#2D5F8C', color:'#fff', fontSize:13, fontWeight:600, padding:'6px 18px', borderRadius:20, zIndex:10, pointerEvents:'none', boxShadow:'0 2px 8px rgba(45,95,140,0.4)' }}>
              {drawStart ? 'Release to finish' : 'Click & drag to draw a room'}
            </div>
          )}
          <canvas
            ref={canvasRef}
            width={860}
            height={Math.round(860 * aspect)}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            style={{
              maxWidth:'calc(100% - 32px)', maxHeight:'calc(100% - 32px)',
              cursor: mode==='draw' ? 'crosshair' : drag?.type==='move' ? 'grabbing' : 'default',
              display:'block', borderRadius:6, boxShadow:'0 2px 20px rgba(0,0,0,0.12)',
            }}
          />
        </div>

        {/* Right: properties */}
        <div style={{ width:220, background:'#fff', borderLeft:'1px solid #EBEBEB', display:'flex', flexDirection:'column', overflow:'hidden' }}>
          {selected ? (
            <div style={{ padding:'16px 14px', overflowY:'auto' }}>
              <div style={{ fontSize:11, fontWeight:700, color:'#9CA3AF', letterSpacing:'0.08em', textTransform:'uppercase', marginBottom:14 }}>Room Properties</div>

              <label style={{ fontSize:12, color:'#6B7280', display:'block', marginBottom:5, fontWeight:500 }}>Name</label>
              <input value={editName} onChange={e => setName(e.target.value)} placeholder="Room name"
                style={{ width:'100%', padding:'8px 10px', background:'#F5F5F4', border:'1px solid #EBEBEB', borderRadius:7, color:'#1A1A1A', fontSize:13, outline:'none', boxSizing:'border-box', marginBottom:14 }} />

              <label style={{ fontSize:12, color:'#6B7280', display:'block', marginBottom:8, fontWeight:500 }}>Color</label>
              <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginBottom:16 }}>
                {PALETTE.map(c => (
                  <div key={c} onClick={() => setColor(c)} style={{ width:22, height:22, borderRadius:5, background:c, cursor:'pointer', border: selected.color===c ? '2px solid #1A1A1A' : '2px solid transparent', boxSizing:'border-box' }} />
                ))}
              </div>

              <div style={{ borderTop:'1px solid #EBEBEB', paddingTop:14, marginBottom:14 }}>
                <label style={{ fontSize:12, color:'#6B7280', display:'block', marginBottom:8, fontWeight:500 }}>Size (3D units)</label>
                <div style={{ display:'flex', gap:8, marginBottom:8 }}>
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:11, color:'#9CA3AF', marginBottom:3 }}>Width</div>
                    <input type="number" step="0.1" min="0.2" value={editW} onChange={e => setEditW(e.target.value)}
                      style={{ width:'100%', padding:'6px 8px', background:'#F5F5F4', border:'1px solid #EBEBEB', borderRadius:6, color:'#1A1A1A', fontSize:13, outline:'none', boxSizing:'border-box' }} />
                  </div>
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:11, color:'#9CA3AF', marginBottom:3 }}>Depth</div>
                    <input type="number" step="0.1" min="0.2" value={editH} onChange={e => setEditH(e.target.value)}
                      style={{ width:'100%', padding:'6px 8px', background:'#F5F5F4', border:'1px solid #EBEBEB', borderRadius:6, color:'#1A1A1A', fontSize:13, outline:'none', boxSizing:'border-box' }} />
                  </div>
                </div>
                <button onClick={applySize} style={{ width:'100%', padding:'7px', borderRadius:7, border:'1px solid #2D5F8C', background:'#F1F5F9', color:'#2D5F8C', fontSize:13, fontWeight:600, cursor:'pointer' }}>
                  Apply Size
                </button>
              </div>

              <button onClick={deleteRoom} style={{ width:'100%', padding:'8px', borderRadius:7, border:'1px solid #FECACA', background:'#FEF2F2', color:'#DC2626', fontSize:13, fontWeight:600, cursor:'pointer' }}>
                Delete Room
              </button>
            </div>
          ) : (
            <div style={{ padding:'16px 14px' }}>
              <div style={{ fontSize:11, fontWeight:700, color:'#9CA3AF', letterSpacing:'0.08em', textTransform:'uppercase', marginBottom:14 }}>Properties</div>
              <div style={{ color:'#9CA3AF', fontSize:13, lineHeight:1.7 }}>
                Select a room to edit it.<br/><br/>
                Drag corners to resize.<br/>
                Drag body to move.
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Custom Delete Confirmation Modal */}
      {floorToDelete !== null && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(15, 15, 15, 0.45)', backdropFilter: 'blur(6px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000,
        }}>
          <div style={{
            background: '#FFFFFF', borderRadius: '16px', width: '400px', maxWidth: '92vw',
            boxShadow: '0 20px 60px rgba(0,0,0,0.18)', border: '1px solid #EBEBEB',
            overflow: 'hidden'
          }}>
            <div style={{ padding: '24px 24px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
              <div style={{
                width: '48px', height: '48px', borderRadius: '50%', background: '#FEF2F2',
                display: 'flex', alignItems: 'center', justifyItems: 'center', justifyContent: 'center', marginBottom: '16px'
              }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#DC2626" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                  <line x1="12" y1="9" x2="12" y2="13"/>
                  <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
              </div>
              <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#111827', margin: '0 0 8px 0', fontFamily: "'Outfit', sans-serif" }}>Delete Floor {floorToDelete + 1}?</h3>
              <p style={{ fontSize: '14px', color: '#6B7280', margin: 0, lineHeight: '1.5' }}>
                This action is permanent and cannot be undone. All rooms and walls on Floor {floorToDelete + 1} will be deleted.
              </p>
            </div>
            <div style={{ display: 'flex', padding: '16px 24px 24px', gap: '10px', justifyContent: 'flex-end', background: '#FAFAFA', borderTop: '1px solid #F3F4F6' }}>
              <button 
                onClick={() => setFloorToDelete(null)}
                style={{
                  padding: '9px 16px', background: '#FFFFFF', color: '#374151',
                  border: '1px solid #D1D5DB', borderRadius: '8px', fontSize: '13.5px', fontWeight: '600', cursor: 'pointer',
                  transition: 'background 0.15s ease'
                }}
              >Cancel</button>
              <button 
                onClick={confirmDeleteFloor}
                style={{
                  padding: '9px 18px', background: '#DC2626', color: '#FFFFFF',
                  border: 'none', borderRadius: '8px', fontSize: '13.5px', fontWeight: '600', cursor: 'pointer',
                  boxShadow: '0 2px 8px rgba(220, 38, 38, 0.25)', transition: 'background 0.15s ease'
                }}
              >Delete Floor</button>
            </div>
          </div>
        </div>
      )}

      {/* Custom Warning/Alert Modal */}
      {alertMessage && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(15, 15, 15, 0.45)', backdropFilter: 'blur(6px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2001,
        }}>
          <div style={{
            background: '#FFFFFF', borderRadius: '16px', width: '380px', maxWidth: '92vw',
            boxShadow: '0 20px 60px rgba(0,0,0,0.18)', border: '1px solid #EBEBEB',
            overflow: 'hidden'
          }}>
            <div style={{ padding: '24px 24px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
              <div style={{
                width: '48px', height: '48px', borderRadius: '50%', background: '#FEF3C7',
                display: 'flex', alignItems: 'center', justifyItems: 'center', justifyContent: 'center', marginBottom: '16px'
              }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#D97706" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="12" y1="8" x2="12" y2="12"/>
                  <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
              </div>
              <h3 style={{ fontSize: '17px', fontWeight: '700', color: '#111827', margin: '0 0 8px 0', fontFamily: "'Outfit', sans-serif" }}>Notice</h3>
              <p style={{ fontSize: '14px', color: '#6B7280', margin: 0, lineHeight: '1.5' }}>
                {alertMessage}
              </p>
            </div>
            <div style={{ display: 'flex', padding: '16px 24px 24px', justifyContent: 'center', background: '#FAFAFA', borderTop: '1px solid #F3F4F6' }}>
              <button 
                onClick={() => setAlertMessage(null)}
                style={{
                  padding: '9px 24px', background: '#111827', color: '#FFFFFF',
                  border: 'none', borderRadius: '8px', fontSize: '13.5px', fontWeight: '600', cursor: 'pointer',
                  transition: 'background 0.15s ease'
                }}
              >Okay</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
