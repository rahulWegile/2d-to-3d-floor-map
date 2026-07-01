import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { FontLoader } from 'three/examples/jsm/loaders/FontLoader';
import { TextGeometry } from 'three/examples/jsm/geometries/TextGeometry';

// Fetch Interceptor for seamless API integration
const originalFetch = window.fetch;
window.fetch = function() {
    let [resource, config] = arguments;
    if (typeof resource === 'string' && resource.startsWith('/')) {
        resource = `http://${window.location.hostname}:8081` + resource;
        config = config || {};
        config.headers = config.headers || {};
        const token = localStorage.getItem('token');
        if (token) config.headers['Authorization'] = 'Bearer ' + token;
    }
    return originalFetch(resource, config);
};

const API_BASE = `http://${window.location.hostname}:8081`;

let scene, camera, renderer, controls;
let raycaster, mouse;
let floorsData = [];
let activeFloorIndex = 0;
let pillarsGroup;

let selectedRoomLabel = null;
let selectedWall = null;

let isDrawingWall = false;
let isAddingRoom = false;
let isDrawingFloor = false;
let outerWallsHidden = false;
let drawStartPoint = null;
let drawPreviewLine = null;
let floorDrawStartPoint = null;
let floorDrawPreview = null;
let animationFrameId = null;

// Project Management State
let currentProjectId = null;
let projectsDB = {};
let currentUserId = localStorage.getItem('archtransform_user_id') || null;
let currentUsername = localStorage.getItem('archtransform_username') || null;

const FLOOR_HEIGHT = 4; // Height per floor
let wallMode = 'pillars'; // 'pillars' | 'walls'

// Generate a brick-pattern bump texture
function createWallBumpTexture() {
    const W = 512, H = 512;
    const canvas = document.createElement('canvas');
    canvas.width = W; canvas.height = H;
    const ctx = canvas.getContext('2d');

    // Dark background (mortar)
    ctx.fillStyle = '#555555';
    ctx.fillRect(0, 0, W, H);

    const brickW = 128, brickH = 48, mortar = 6;
    const rows = Math.ceil(H / (brickH + mortar)) + 1;
    const cols = Math.ceil(W / (brickW + mortar)) + 1;

    for (let row = 0; row < rows; row++) {
        const offsetX = (row % 2) * (brickW / 2);
        const y = row * (brickH + mortar);
        for (let col = -1; col < cols; col++) {
            const x = col * (brickW + mortar) - offsetX;
            // Brick face with slight brightness variation
            const bright = 180 + Math.floor(Math.random() * 40);
            ctx.fillStyle = `rgb(${bright},${bright},${bright})`;
            ctx.fillRect(x + mortar, y + mortar, brickW - mortar, brickH - mortar);
        }
    }

    const tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(2, 2);
    return tex;
}

const _wallBumpTex = createWallBumpTexture();

// Base Materials (these will be synced with the UI color pickers)
const wallMat = new THREE.MeshStandardMaterial({
    color: 0x94a3b8,
    roughness: 0.8,
    bumpMap: _wallBumpTex,
    bumpScale: 0.6,
});
const wallSelectedMat = new THREE.MeshStandardMaterial({ color: 0xffa502, roughness: 0.5, emissive: 0xffa502, emissiveIntensity: 0.2 });

export function initEngine(projectId) {
    // Avoid double initialization
    if (renderer) return;
    
    currentProjectId = projectId;
    const container = document.getElementById('canvas-container');
    if (container) {
        scene = new THREE.Scene();
        scene.background = new THREE.Color(0xf1f5f9);

        camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 1, 1000);
        camera.position.set(0, 30, 30);

        renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true });
        renderer.setSize(container.clientWidth, container.clientHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.shadowMap.enabled = true;
        container.appendChild(renderer.domElement);

        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;

        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambientLight);

        const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
        dirLight.position.set(20, 40, 20);
        dirLight.castShadow = true;
        scene.add(dirLight);

        raycaster = new THREE.Raycaster();
        mouse = new THREE.Vector2();

        pillarsGroup = new THREE.Group();
        scene.add(pillarsGroup);

        window.addEventListener('resize', onWindowResize);
        renderer.domElement.addEventListener('click', onClick);
        renderer.domElement.addEventListener('mousemove', onMouseMove);
    }

    setupUI();
    
    // Auto-load dashboard if on dashboard page
    if (document.getElementById('project-list')) {
        window.loadDashboard();
    }

    // Auto-load editor project if on editor page
    if (document.getElementById('app')) {
        if (currentProjectId) {
            loadEditorProject(currentProjectId);
        } else {
            buildBuilding([]);
        }
    }
    animate();
}

export function cleanupEngine() {
    window.removeEventListener('resize', onWindowResize);
    window.removeEventListener('keydown', onKeyDown);
    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
    }
    if (renderer && renderer.domElement) {
        renderer.domElement.remove();
        renderer.dispose();
    }
    renderer = null;
    scene = null;
    hiddenLabelFloors.clear();
}

// Per-floor label visibility — tracks floor indices where labels are hidden
const hiddenLabelFloors = new Set();

export function toggleFloorLabels(floorIndex) {
    if (hiddenLabelFloors.has(floorIndex)) {
        hiddenLabelFloors.delete(floorIndex);
        return true;  // now visible
    } else {
        hiddenLabelFloors.add(floorIndex);
        return false; // now hidden
    }
}

export function isFloorLabelsVisible(floorIndex) {
    return !hiddenLabelFloors.has(floorIndex);
}

export function getFloorCount() {
    return floorsData.length;
}

function saveSettingsLocally() {
    if (!currentProjectId) return;
    const settings = {
        wallColor: document.getElementById('wall-color-picker')?.value || '#94a3b8',
        floorColor: document.getElementById('floor-color-picker')?.value || '#e2e8f0',
        bgColor: document.getElementById('bg-color-picker')?.value || '#f1f5f9',
        wallOpacity: document.getElementById('wall-opacity-slider')?.value || '1',
        floorOpacity: document.getElementById('floor-opacity-slider')?.value || '1',
    };
    localStorage.setItem(`proj_settings_${currentProjectId}`, JSON.stringify(settings));
}

function applySettings(settings) {
    if (!settings) return;

    if (settings.wallColor) {
        const picker = document.getElementById('wall-color-picker');
        if (picker) picker.value = settings.wallColor;
        wallMat.color.set(settings.wallColor);
        wallMat.needsUpdate = true;
    }
    if (settings.floorColor) {
        const picker = document.getElementById('floor-color-picker');
        if (picker) picker.value = settings.floorColor;
    }
    if (settings.bgColor && scene) {
        const picker = document.getElementById('bg-color-picker');
        if (picker) picker.value = settings.bgColor;
        scene.background = new THREE.Color(settings.bgColor);
    }
    if (settings.wallOpacity !== undefined) {
        const slider = document.getElementById('wall-opacity-slider');
        const label = document.getElementById('wall-opacity-val');
        const op = parseFloat(settings.wallOpacity);
        if (slider) slider.value = op;
        if (label) label.innerText = Math.round(op * 100) + '%';
        wallMat.transparent = op < 1;
        wallMat.opacity = op;
        wallMat.needsUpdate = true;
    }
    if (settings.floorOpacity !== undefined) {
        const slider = document.getElementById('floor-opacity-slider');
        const label = document.getElementById('floor-opacity-val');
        const op = parseFloat(settings.floorOpacity);
        if (slider) slider.value = op;
        if (label) label.innerText = Math.round(op * 100) + '%';
    }
}

async function loadEditorProject(projectId) {
    const userId = document.getElementById('app').dataset.userid || currentUserId;
    try {
        const loading = document.getElementById('loading');
        if (loading) loading.style.display = 'flex';

        const res = await fetch(`/projects/${userId}?t=${Date.now()}`);
        if (!res.ok) throw new Error("Could not fetch projects");
        const data = await res.json();

        const proj = data.projects.find(p => p.project_id === projectId);
        if (proj) {
            currentProjectId = proj.project_id;
            const localSettings = localStorage.getItem(`proj_settings_${proj.project_id}`);
            applySettings(localSettings ? JSON.parse(localSettings) : proj.settings);
            buildBuilding(proj.rawBackendData || []);
            setTimeout(onWindowResize, 100); // Ensure canvas gets sized after layout completes
        } else {
            alert("Project not found");
        }
    } catch(e) {
        console.error(e);
        alert("Error loading project");
    } finally {
        const loading = document.getElementById('loading');
        if (loading) loading.style.display = 'none';
    }
}

async function appLogin(e) {
    if (e) e.preventDefault();
    const un = document.getElementById('login-username').value;
    const pw = document.getElementById('login-password').value;
    if(!un || !pw) return alert("Please enter username and password");
    
    let payload = {username: un, password: pw};
    
    const isSignup = !!document.getElementById('signup-email');
    if (isSignup) {
        const email = document.getElementById('signup-email').value;
        const confirmPw = document.getElementById('signup-password-confirm').value;
        if (!email) return alert("Please enter an email address");
        if (pw !== confirmPw) return alert("Passwords do not match");
        payload.email = email;
    }
    
    const endpoint = isSignup ? `/auth/signup` : `/auth/login`;

    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || "Authentication failed");
            return;
        }

        const data = await res.json();
        localStorage.setItem('archtransform_user_id', data.user_id);
        localStorage.setItem('archtransform_username', data.username);
        
        window.location.href = '/dashboard';
    } catch (e) {
        alert("Error connecting to server");
        console.error(e);
    }
}

window.loadDashboard = async function() {
    const userId = document.getElementById('dashboard-screen').dataset.userid || currentUserId;
    if (!userId) return;
    
    try {
        const res = await fetch(`/projects/${userId}`);
        if (!res.ok) throw new Error("Could not fetch projects. You may need to log in again.");
        const data = await res.json();
        
        const grid = document.getElementById('project-list');
        
        projectsDB = {};
        data.projects.forEach(p => projectsDB[p.project_id] = p);
        
        grid.innerHTML = '';
        if (data.projects.length === 0) {
            grid.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 80px 20px; animation: fadeInUp 0.6s ease-out;">
                    <div style="width: 80px; height: 80px; background: linear-gradient(135deg, rgba(56,189,248,0.1), rgba(139,92,246,0.1)); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 24px auto; border: 1px solid rgba(56,189,248,0.2);">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>
                    </div>
                    <h3 style="font-family: 'Outfit', sans-serif; font-size: 24px; color: #ffffff; margin-bottom: 8px;">No projects yet</h3>
                    <p style="color: #94a3b8; max-width: 320px; margin: 0 auto; font-size: 15px;">Create your first architectural project by uploading a floor plan blueprint.</p>
                </div>
            `;
            return;
        }
        
        data.projects.forEach(proj => {
            const card = document.createElement('div');
            card.className = 'modern-project-card';
            const numFloors = proj.rawBackendData ? proj.rawBackendData.length : 0;
            const dateStr = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
            card.innerHTML = `
                <div class="card-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
                </div>
                <h3 class="card-title">${proj.name}</h3>
                <p class="card-subtitle">${numFloors} Floor${numFloors !== 1 ? 's' : ''} • 3D Model</p>
                <div class="card-footer">
                    <span>Updated ${dateStr}</span>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                </div>
            `;
            card.addEventListener('click', () => {
                window.location.href = `/annotate?project_id=${proj.project_id}`;
            });
            grid.appendChild(card);
        });
    } catch(e) {
        const grid = document.getElementById('project-list');
        grid.innerHTML = '<p style="color: #ef4444; grid-column: 1/-1;">Error loading projects from database.</p>';
    }
}

window.appNewProject = function() {
    document.getElementById('upload-screen').style.display = 'block';
    document.getElementById('dashboard-screen').style.display = 'none';
}

window.openProject = function(id) {
    window.location.href = '/annotate?project_id=' + id;
}

function saveProjectsDB() {
    localStorage.setItem('archtransform_projects', JSON.stringify(projectsDB));
}

function getActiveFloor() {
    return floorsData[activeFloorIndex];
}

function setupUI() {
    // Sync initial colors and opacity from the UI
    const initialWallColor = document.getElementById('wall-color-picker')?.value;
    if (initialWallColor) {
        wallMat.color.copy(new THREE.Color(initialWallColor));
    }
    const initialWallOpacity = document.getElementById('wall-opacity-slider')?.value;
    if (initialWallOpacity) {
        const op = parseFloat(initialWallOpacity);
        wallMat.transparent = op < 1;
        wallMat.opacity = op;
    }
    
    // Initial sync for floor opacity
    const initialFloorOpacity = document.getElementById('floor-opacity-slider')?.value;
    if (initialFloorOpacity) {
        // Will apply dynamically in buildBuilding or when slider changes
    }

    // --- WORKFLOW EVENT BINDINGS ---
    document.querySelector('.login-form-container')?.addEventListener('submit', appLogin);
    const logoutBtns = document.querySelectorAll('#btn-logout, #nav-btn-logout');
    logoutBtns.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            localStorage.removeItem('archtransform_user_id');
            localStorage.removeItem('archtransform_username');
            try {
                await fetch('/auth/logout', { method: 'POST' });
            } catch(e) {}
            window.location.href = '/login';
        });
    });
    document.getElementById('btn-new-project')?.addEventListener('click', window.appNewProject);
    document.getElementById('btn-cancel-upload')?.addEventListener('click', () => {
        document.getElementById('upload-screen').style.display = 'none';
        document.getElementById('dashboard-screen').style.display = 'block';
    });
    document.getElementById('btn-back-dashboard')?.addEventListener('click', () => {
        window.location.href = '/dashboard';
    });

    const dropZone = document.getElementById('drop-zone');
    dropZone?.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
    dropZone?.addEventListener('dragleave', () => { dropZone.classList.remove('dragover'); });
    dropZone?.addEventListener('drop', (e) => {
        e.preventDefault(); dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) handleFileUpload(e.dataTransfer.files);
    });

    document.getElementById('file-upload')?.addEventListener('change', (e) => {
        if (e.target.files.length) handleFileUpload(e.target.files);
    });

    document.getElementById('bg-color-picker')?.addEventListener('input', (e) => { scene.background = new THREE.Color(e.target.value); saveSettingsLocally(); });

    document.getElementById('floor-selector')?.addEventListener('change', (e) => {
        activeFloorIndex = parseInt(e.target.value);
        updateFloorVisibility();
        deselectAll();
    });

    document.getElementById('delete-floor-btn')?.addEventListener('click', deleteActiveFloor);
    
    document.getElementById('save-project-btn')?.addEventListener('click', () => {
        saveSettingsLocally();
        saveCurrentProject();
    });

    // Floor upload listener is now handled by React in Editor.jsx

    document.getElementById('stack-floors-mode')?.addEventListener('change', () => {
        updateFloorVisibility();
        deselectAll();
    });

    document.getElementById('show-blueprint')?.addEventListener('change', (e) => {
        updateFloorVisibility();
    });

    document.getElementById('floor-color-picker')?.addEventListener('input', (e) => {
        floorsData.forEach(f => {
            if (f.floorMesh && f.floorMesh.material) {
                if (!document.getElementById('show-blueprint').checked) {
                    f.floorMesh.material.color.set(e.target.value);
                    f.floorMesh.material.needsUpdate = true;
                }
            }
        });
    });

    document.getElementById('floor-opacity-slider')?.addEventListener('input', (e) => {
        const opacity = parseFloat(e.target.value);
        const isTransparent = opacity < 1;
        const valLabel = document.getElementById('floor-opacity-val');
        if (valLabel) valLabel.innerText = Math.round(opacity * 100) + '%';
        
        floorsData.forEach(f => {
            if (f.floorMesh && f.floorMesh.material) {
                f.floorMesh.material.transparent = isTransparent;
                f.floorMesh.material.opacity = opacity;
                f.floorMesh.material.depthWrite = opacity === 1;
                f.floorMesh.material.needsUpdate = true;
            }
            f.roomLabels.forEach(room => {
                if (room.mesh && room.mesh.material) {
                    room.mesh.material.transparent = isTransparent;
                    room.mesh.material.opacity = opacity;
                    room.mesh.material.needsUpdate = true;
                }
            });
        });
    });

    document.getElementById('wall-color-picker')?.addEventListener('input', (e) => {
        const color = new THREE.Color(e.target.value);
        wallMat.color.copy(color);
        floorsData.forEach(f => {
            f.wallsGroup.children.forEach(wall => {
                if (wall !== selectedWall) {
                    wall.material.color.copy(color);
                }
            });
        });
        if (pillarsGroup) {
            pillarsGroup.children.forEach(p => {
                p.material.color.copy(color);
            });
        }
        saveSettingsLocally();
    });

    document.getElementById('wall-opacity-slider')?.addEventListener('input', (e) => {
        const opacity = parseFloat(e.target.value);
        const isTransparent = opacity < 1;
        const valLabel = document.getElementById('wall-opacity-val');
        if (valLabel) valLabel.innerText = Math.round(opacity * 100) + '%';
        
        wallMat.transparent = isTransparent;
        wallMat.opacity = opacity;
        
        floorsData.forEach(f => {
            f.wallsGroup.children.forEach(wall => {
                if (wall !== selectedWall) {
                    wall.material.transparent = isTransparent;
                    wall.material.opacity = opacity;
                    wall.material.needsUpdate = true;
                }
            });
        });
        
        if (pillarsGroup) {
            pillarsGroup.children.forEach(p => {
                p.material.transparent = isTransparent;
                p.material.opacity = opacity;
                p.material.needsUpdate = true;
            });
        }
    });

    document.getElementById('room-name-input')?.addEventListener('input', (e) => {
        if (selectedRoomLabel) {
            selectedRoomLabel.name = e.target.value;
            if (selectedRoomLabel.element) {
                selectedRoomLabel.element.innerText = e.target.value;
                selectedRoomLabel.element.style.display = e.target.value.trim() ? 'block' : 'none';
            }
            const btn = document.getElementById(`iso-btn-${selectedRoomLabel.layerIndex}`);
            if (btn) btn.innerText = `Layer ${selectedRoomLabel.layerIndex}: ${e.target.value}`;
        }
    });

    document.getElementById('room-color-picker')?.addEventListener('input', (e) => {
        if (selectedRoomLabel) selectedRoomLabel.mesh.material.color.set(e.target.value);
    });

    document.getElementById('draw-wall-btn')?.addEventListener('click', () => {
        const drawBtn = document.getElementById('draw-wall-btn');
        const drawFloorBtn = document.getElementById('draw-floor-btn');
        if (!getActiveFloor()) return;
        isDrawingWall = !isDrawingWall;
        isAddingRoom = false;
        isDrawingFloor = false;
        if(drawBtn) drawBtn.style.background = isDrawingWall ? '#00b894' : '';
        if(drawBtn) drawBtn.style.color = isDrawingWall ? '#fff' : '';
        if(drawBtn) drawBtn.innerText = 'Draw Wall';
        if(drawFloorBtn) drawFloorBtn.style.background = '';
        if(drawFloorBtn) drawFloorBtn.style.color = '';
        if(drawFloorBtn) drawFloorBtn.innerText = 'Draw Room Floor';
        drawStartPoint = null;
        floorDrawStartPoint = null;
        if(drawPreviewLine) { scene.remove(drawPreviewLine); drawPreviewLine = null; }
        if(floorDrawPreview) { scene.remove(floorDrawPreview); floorDrawPreview.geometry.dispose(); floorDrawPreview = null; }
        deselectAll();
    });

    document.getElementById('draw-floor-btn')?.addEventListener('click', () => {
        const drawBtn = document.getElementById('draw-wall-btn');
        const drawFloorBtn = document.getElementById('draw-floor-btn');
        if (!getActiveFloor()) return;
        isDrawingFloor = !isDrawingFloor;
        isDrawingWall = false;
        isAddingRoom = false;
        if(drawFloorBtn) drawFloorBtn.style.background = isDrawingFloor ? '#00b894' : '';
        if(drawFloorBtn) drawFloorBtn.style.color = isDrawingFloor ? '#fff' : '';
        if(drawFloorBtn) drawFloorBtn.innerText = 'Draw Room Floor';
        if(drawBtn) drawBtn.style.background = '';
        if(drawBtn) drawBtn.style.color = '';
        if(drawBtn) drawBtn.innerText = 'Draw Wall';
        drawStartPoint = null;
        floorDrawStartPoint = null;
        if(drawPreviewLine) { scene.remove(drawPreviewLine); drawPreviewLine = null; }
        if(floorDrawPreview) { scene.remove(floorDrawPreview); floorDrawPreview.geometry.dispose(); floorDrawPreview = null; }
        deselectAll();
    });

    const outerWallsBtn = document.getElementById('remove-outer-walls-btn');
    outerWallsBtn?.addEventListener('click', () => {
        outerWallsHidden = !outerWallsHidden;
        outerWallsBtn.innerText = outerWallsHidden ? 'Show Outer Walls' : 'Hide Outer Walls';
        outerWallsBtn.style.background = outerWallsHidden ? '#00b894' : '';
        outerWallsBtn.style.color = outerWallsHidden ? '#fff' : '';

        floorsData.forEach(f => {
            let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
            f.wallsGroup.children.forEach(mesh => {
                if (mesh.userData.isOuter === undefined) {
                    mesh.geometry.computeBoundingBox();
                    const box = new THREE.Box3().setFromObject(mesh);
                    minX = Math.min(minX, box.min.x);
                    maxX = Math.max(maxX, box.max.x);
                    minZ = Math.min(minZ, box.min.z);
                    maxZ = Math.max(maxZ, box.max.z);
                }
            });
            
            f.wallsGroup.children.forEach(mesh => {
                if (mesh.userData.isOuter === undefined) {
                    const wLen = mesh.geometry.parameters.depth;
                    const dir = new THREE.Vector3(0,0,1).applyQuaternion(mesh.quaternion);
                    const start = mesh.position.clone().add(dir.clone().multiplyScalar(-wLen/2));
                    const end = mesh.position.clone().add(dir.clone().multiplyScalar(wLen/2));

                    const margin = 1.0; 
                    const isOuter = 
                        (start.x <= minX + margin && end.x <= minX + margin) || 
                        (start.x >= maxX - margin && end.x >= maxX - margin) || 
                        (start.z <= minZ + margin && end.z <= minZ + margin) || 
                        (start.z >= maxZ - margin && end.z >= maxZ - margin);
                        
                    mesh.userData.isOuter = isOuter;
                }
                
                if (mesh.userData.isOuter) {
                    mesh.visible = !outerWallsHidden;
                }
            });
        });
        deselectAll();
    });


    document.getElementById('delete-btn')?.addEventListener('click', () => {
        if (selectedWall) {
            if (pillarsGroup.children.includes(selectedWall)) {
                pillarsGroup.remove(selectedWall);
            } else {
                floorsData.forEach(f => {
                    if (f.wallsGroup.children.includes(selectedWall)) {
                        f.wallsGroup.remove(selectedWall);
                    }
                });
            }
            if (selectedWall.geometry) selectedWall.geometry.dispose();
            if (selectedWall.material) selectedWall.material.dispose();
            selectedWall = null;
            const delBtn = document.getElementById('delete-btn');
            if (delBtn) delBtn.style.display = 'none';
            document.getElementById('no-selection').style.display = 'block';
            document.getElementById('no-selection').innerText = 'Select a room floor to edit it.';
        } else if (selectedRoomLabel) {
            selectedRoomLabel.element.remove();
            scene.remove(selectedRoomLabel.mesh);
            if (selectedRoomLabel.mesh.geometry) selectedRoomLabel.mesh.geometry.dispose();
            if (selectedRoomLabel.mesh.material) selectedRoomLabel.mesh.material.dispose();
            floorsData.forEach(f => {
                f.roomLabels = f.roomLabels.filter(l => l !== selectedRoomLabel);
            });
            selectedRoomLabel = null;
            document.getElementById('selection-details').style.display = 'none';
            document.getElementById('no-selection').style.display = 'block';
        }
        const delBtn = document.getElementById('delete-btn');
        if (delBtn) delBtn.style.display = 'none';
    });

    window.removeEventListener('keydown', onKeyDown);
    window.addEventListener('keydown', onKeyDown);
}

function onKeyDown(e) {
    if (document.activeElement && document.activeElement.tagName === 'INPUT') return;
        
        if (e.key === 'Delete' || e.key === 'Backspace') {
            const delBtn = document.getElementById('delete-btn');
            if (delBtn.style.display !== 'none') {
                if (selectedWall) {
                    if (pillarsGroup.children.includes(selectedWall)) {
                        pillarsGroup.remove(selectedWall);
                    } else {
                        floorsData.forEach(f => {
                            if (f.wallsGroup.children.includes(selectedWall)) {
                                f.wallsGroup.remove(selectedWall);
                            }
                        });
                    }
                    if (selectedWall.geometry) selectedWall.geometry.dispose();
                    if (selectedWall.material) selectedWall.material.dispose();
                    selectedWall = null;
                    const deleteBtn = document.getElementById('delete-btn');
                    if (deleteBtn) deleteBtn.style.display = 'none';
                    document.getElementById('no-selection').style.display = 'block';
                    document.getElementById('no-selection').innerText = 'Select a room floor to edit it.';
                } else {
                    delBtn.click();
                }
            }
            return;
        }
        
        const moveSpeed = 0.25;
        const scaleSpeed = 0.25;
        
        if (selectedWall) {
            switch (e.key) {
                case 'ArrowUp': selectedWall.position.z -= moveSpeed; break;
                case 'ArrowDown': selectedWall.position.z += moveSpeed; break;
                case 'ArrowLeft': selectedWall.position.x -= moveSpeed; break;
                case 'ArrowRight': selectedWall.position.x += moveSpeed; break;
            }
        } else if (selectedRoomLabel) {
            if (e.shiftKey) {
                switch (e.key) {
                    case 'ArrowUp': selectedRoomLabel.mesh.scale.y += scaleSpeed; break;
                    case 'ArrowDown': selectedRoomLabel.mesh.scale.y = Math.max(0.1, selectedRoomLabel.mesh.scale.y - scaleSpeed); break;
                    case 'ArrowLeft': selectedRoomLabel.mesh.scale.x = Math.max(0.1, selectedRoomLabel.mesh.scale.x - scaleSpeed); break;
                    case 'ArrowRight': selectedRoomLabel.mesh.scale.x += scaleSpeed; break;
                }
            } else {
                switch (e.key) {
                    case 'ArrowUp': selectedRoomLabel.mesh.position.z -= moveSpeed; break;
                    case 'ArrowDown': selectedRoomLabel.mesh.position.z += moveSpeed; break;
                    case 'ArrowLeft': selectedRoomLabel.mesh.position.x -= moveSpeed; break;
                    case 'ArrowRight': selectedRoomLabel.mesh.position.x += moveSpeed; break;
                }
            }
        }
    }

async function handleFileUpload(files) {
    const status = document.getElementById('upload-status');
    const loading = document.getElementById('loading');
    status.innerText = 'Uploading...';
    if (loading) loading.style.display = 'flex';

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    try {
        const response = await fetch(`/upload`, { method: 'POST', body: formData });
        if (!response.ok) throw new Error('Upload failed');
        const data = await response.json();
        
        const projName = document.getElementById('new-project-name').value || 'Untitled Project';
        const userId = document.getElementById('dashboard-screen')?.dataset?.userid || currentUserId;
        
        const saveRes = await fetch(`/projects/save`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: userId,
                project_id: null,
                name: projName,
                rawBackendData: data.floors
            })
        });
        
        if (!saveRes.ok) throw new Error("Database save failed");
        const savedData = await saveRes.json();
        
        status.innerText = 'Success!';

        // Navigate to annotation page first
        setTimeout(() => {
            window.location.href = '/annotate?project_id=' + savedData.project_id;
        }, 500);
        
    } catch (error) {
        console.error('Error:', error);
        status.innerText = 'Error: ' + error.message;
    } finally {
        const loading = document.getElementById('loading');
        if (loading) loading.style.display = 'none';
        setTimeout(() => { status.innerText = ''; }, 3000);
    }
}

function updateFloorSelector() {
    const selector = document.getElementById('floor-selector');
    if (!selector) return;
    selector.innerHTML = '';
    floorsData.forEach((f, idx) => {
        const opt = document.createElement('option');
        opt.value = idx;
        opt.innerText = `Floor ${idx + 1}`;
        selector.appendChild(opt);
    });
    if (floorsData.length > 0) {
        selector.value = activeFloorIndex;
    }
}

function updatePillarsHeight() {
    if (!pillarsGroup) return;

    // Dispose unique geometries/materials only once (meshes within a floor share them)
    const seenGeos = new Set();
    const seenMats = new Set();
    while (pillarsGroup.children.length > 0) {
        const p = pillarsGroup.children[0];
        pillarsGroup.remove(p);
        if (p.geometry && !seenGeos.has(p.geometry)) { seenGeos.add(p.geometry); p.geometry.dispose(); }
        if (p.material && !seenMats.has(p.material)) { seenMats.add(p.material); p.material.dispose(); }
    }
    
    // Outer poles have been completely removed as requested
    return;
}

function updateFloorVisibility() {
    const showBlueprint = document.getElementById('show-blueprint').checked;
    const floorColor = document.getElementById('floor-color-picker').value;
    const isStacked = document.getElementById('stack-floors-mode').checked;

    floorsData.forEach((f, idx) => {
        const isActive = (idx === activeFloorIndex);
        const isVisible = isStacked || isActive;
        
        f.floorMesh.visible = isVisible;
        f.wallsGroup.visible = isVisible;
        f.isVisible = isVisible;
        
        const targetY = isStacked ? f.yOffset : 0;
        f.floorMesh.position.y = targetY;
        f.wallsGroup.position.y = targetY;
        f.roomLabels.forEach(l => {
            const yStackOffset = 0.05 + ((l.layerIndex || 1) - 1) * 0.8;
            l.mesh.position.y = targetY + yStackOffset;
            if (l.center) l.center.y = targetY + yStackOffset;
            l.mesh.visible = isVisible;
        });

        // Floor Mesh:
        const sliderOp = parseFloat(document.getElementById('floor-opacity-slider')?.value || "1");
        
        if (isVisible && showBlueprint && f.texture) {
            f.floorMesh.material.map = f.texture;
            f.floorMesh.material.color.setHex(0xffffff);
        } else {
            f.floorMesh.material.map = null;
            f.floorMesh.material.color.set(floorColor);
        }
        
        f.floorMesh.material.transparent = sliderOp < 1;
        f.floorMesh.material.opacity = sliderOp;
        f.floorMesh.material.depthWrite = sliderOp === 1;
        
        f.floorMesh.material.needsUpdate = true;
    });

    updatePillarsHeight();
    
    if (pillarsGroup) {
        pillarsGroup.children.forEach(p => {
            const fIdx = p.userData.floorIndex;
            const isVisible = isStacked || (fIdx === activeFloorIndex);
            p.visible = isVisible;
        });
    }
}

function buildBuilding(floorsArr) {
    // Clear existing
    floorsData.forEach(f => {
        scene.remove(f.floorMesh);
        scene.remove(f.wallsGroup);
        f.roomLabels.forEach(l => { l.element.remove(); scene.remove(l.mesh); });
    });
    while(pillarsGroup.children.length > 0) {
        pillarsGroup.remove(pillarsGroup.children[0]);
    }

    floorsData = [];
    activeFloorIndex = 0;
    deselectAll();

    const selector = document.getElementById('floor-selector');
    selector.innerHTML = '';

    const textureLoader = new THREE.TextureLoader();

    floorsArr.forEach((floor, idx) => {
        const yOffset = idx * FLOOR_HEIGHT;
        const aspect = floor.height / floor.width;
        const floorWidth = 20;
        const floorHeight = 20 * aspect;
        
        const floorGeo = new THREE.PlaneGeometry(floorWidth, floorHeight);
        const initialFloorOp = parseFloat(document.getElementById('floor-opacity-slider')?.value || "1");
        const floorMat = new THREE.MeshStandardMaterial({ 
            color: document.getElementById('floor-color-picker').value, 
            roughness: 0.8,
            transparent: initialFloorOp < 1,
            opacity: initialFloorOp
        });
        const fMesh = new THREE.Mesh(floorGeo, floorMat);
        fMesh.rotation.x = -Math.PI / 2;
        fMesh.position.y = yOffset;
        fMesh.receiveShadow = true;
        scene.add(fMesh);

        const wGroup = new THREE.Group();
        wGroup.position.y = yOffset;
        scene.add(wGroup);

        let fMinX = Infinity, fMaxX = -Infinity, fMinZ = Infinity, fMaxZ = -Infinity;
        let fHasWalls = false;
        if (floor.walls) {
            floor.walls.forEach(wall => {
                // Support both {points:[{x,z},{x,z}]} and legacy {x1,y1,x2,y2} formats
                const pts = wall.points && wall.points.length === 2
                    ? wall.points
                    : (wall.x1 != null ? [{x: wall.x1, z: wall.y1}, {x: wall.x2, z: wall.y2}] : null);
                if (!pts) return;
                fHasWalls = true;
                fMinX = Math.min(fMinX, pts[0].x, pts[1].x);
                fMaxX = Math.max(fMaxX, pts[0].x, pts[1].x);
                fMinZ = Math.min(fMinZ, pts[0].z, pts[1].z);
                fMaxZ = Math.max(fMaxZ, pts[0].z, pts[1].z);
            });
        }
        if (!fHasWalls) {
            fMinX = -10; fMaxX = 10;
            fMinZ = -10 * aspect; fMaxZ = 10 * aspect;
        }

        const newFloor = {
            floorMesh: fMesh,
            wallsGroup: wGroup,
            roomLabels: [],
            yOffset: yOffset,
            imageUrl: floor.imageUrl,
            texture: null,
            originalWalls: floor.walls || [],
            bounds: { minX: fMinX, maxX: fMaxX, minZ: fMinZ, maxZ: fMaxZ }
        };
        floorsData.push(newFloor);

        if (floor.imageUrl) {
            const finalUrl = floor.imageUrl.startsWith('/') ? API_BASE + floor.imageUrl : floor.imageUrl;
            textureLoader.load(finalUrl, (texture) => {
                texture.colorSpace = THREE.SRGBColorSpace;
                newFloor.texture = texture;
                if (idx === activeFloorIndex && document.getElementById('show-blueprint').checked) {
                    fMesh.material.map = texture;
                    fMesh.material.color.setHex(0xffffff);
                    fMesh.material.needsUpdate = true;
                }
            });
        }

        if (floor.walls) {
            floor.walls.forEach(wall => {
                // Support both {points:[{x,z},{x,z}]} and legacy {x1,y1,x2,y2} formats
                const pts = wall.points && wall.points.length === 2
                    ? wall.points
                    : (wall.x1 != null ? [{x: wall.x1, z: wall.y1}, {x: wall.x2, z: wall.y2}] : null);
                if (!pts) return;
                const start = new THREE.Vector3(pts[0].x, 0, pts[0].z);
                const end = new THREE.Vector3(pts[1].x, 0, pts[1].z);
                createManualWall(start, end, newFloor);
            });
        }

        if (floor.rooms) {
            floor.rooms.forEach(room => {
                const pos = new THREE.Vector3(room.x, yOffset, room.z);
                if (room.polygon && room.polygon.length >= 3) {
                    createPolygonRoom(room, newFloor, yOffset);
                } else {
                    createNewRoomMarker(pos, room.name, false, newFloor, room.w || 2, room.h || 2, true, false, room);
                }
            });
        }

        const opt = document.createElement('option');
        opt.value = idx;
        opt.innerText = `Floor ${idx + 1}`;
        selector.appendChild(opt);
    });


    updateFloorVisibility();
}

export async function saveCurrentProject() {
    const btn = document.getElementById('save-project-btn');
    if (btn) btn.innerText = 'Saving...';
    
    try {
        const payload = floorsData.map(f => {
            // Preserve original wall data — wGroup has no children while createManualWall is a stub,
            // so reconstructing from mesh geometry always yields []. Use the data loaded from backend.
            const walls = f.originalWalls || [];
            
            const groups = {};
            f.roomLabels.forEach(l => {
                const gid = l.groupId || 'legacy_' + Math.random();
                if (!groups[gid]) groups[gid] = { layers: [], base: l };
                groups[gid].layers.push({
                    name: l.name || l.element.innerText,
                    layerIndex: l.layerIndex || 1,
                    color: l.color
                });
            });

            const rooms = Object.values(groups).map(g => {
                const base = g.base;
                const r = {
                    x: (base.center ? base.center.x : 0) + base.mesh.position.x,
                    z: (base.center ? base.center.z : 0) + base.mesh.position.z,
                    name: g.layers.find(ly => ly.layerIndex === 1)?.name || base.name || base.element.innerText || '',
                    groupId: base.groupId,
                    layers: g.layers
                };
                if (base.polygon) {
                    r.polygon = base.polygon.map(p => ({
                        x: p.x + base.mesh.position.x,
                        z: p.z + base.mesh.position.z
                    }));
                }
                if (base.w) r.w = base.w;
                if (base.h) r.h = base.h;
                return r;
            });
            
            return {
                width: 20,
                height: 20 * (f.floorMesh.geometry.parameters.height / f.floorMesh.geometry.parameters.width),
                imageUrl: f.imageUrl,
                walls: walls,
                rooms: rooms
            };
        });

        const userId = document.getElementById('app').dataset.userid || currentUserId;
        
        let projName = "Untitled Project";
        if (currentProjectId) {
            const dbRes = await fetch(`/projects/${userId}`);
            if (dbRes.ok) {
                const dbData = await dbRes.json();
                const proj = dbData.projects.find(p => p.project_id === currentProjectId);
                if (proj) projName = proj.name;
            }
        }
        
        const res = await fetch(`/projects/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: userId,
                project_id: currentProjectId || null,
                name: projName,
                rawBackendData: payload,
                settings: {
                    wallColor: document.getElementById('wall-color-picker')?.value || '#94a3b8',
                    floorColor: document.getElementById('floor-color-picker')?.value || '#e2e8f0',
                    bgColor: document.getElementById('bg-color-picker')?.value || '#f1f5f9',
                    wallOpacity: document.getElementById('wall-opacity-slider')?.value || '1',
                    floorOpacity: document.getElementById('floor-opacity-slider')?.value || '1',
                }
            })
        });
        
        if (!res.ok) throw new Error("Save failed");
        
        if (btn) {
            btn.innerText = 'Saved!';
            btn.style.background = 'var(--btn-success, #10b981)';
            setTimeout(() => {
                btn.innerText = '💾 Save Project';
                btn.style.background = 'var(--btn-primary)';
            }, 2000);
        }
    } catch(e) {
        console.error(e);
        if (btn) {
            btn.innerText = 'Error Saving';
            btn.style.background = 'var(--btn-danger)';
            setTimeout(() => {
                btn.innerText = '💾 Save Project';
                btn.style.background = 'var(--btn-primary)';
            }, 2000);
        }
    }
}

async function deleteActiveFloor() {
    if (floorsData.length === 0) return;

    // Show custom modal
    const modal = document.getElementById('delete-confirm-modal');
    const title = document.getElementById('delete-modal-title');
    if (modal && title) {
        title.innerText = `Delete Floor ${activeFloorIndex + 1}?`;
        modal.style.display = 'flex';
        // Allow a slight delay for display: flex to apply before adding visible class for transition
        setTimeout(() => modal.classList.add('visible'), 10);
        
        // Wait for user interaction
        const result = await new Promise((resolve) => {
            const btnCancel = document.getElementById('btn-cancel-delete');
            const btnConfirm = document.getElementById('btn-confirm-delete');
            
            const onCancel = () => { cleanup(); resolve(false); };
            const onConfirm = () => { cleanup(); resolve(true); };
            
            const cleanup = () => {
                modal.classList.remove('visible');
                setTimeout(() => modal.style.display = 'none', 300);
                btnCancel.removeEventListener('click', onCancel);
                btnConfirm.removeEventListener('click', onConfirm);
            };
            
            btnCancel.addEventListener('click', onCancel);
            btnConfirm.addEventListener('click', onConfirm);
        });
        
        if (!result) return;
    } else {
        // Fallback to native if modal is missing
        if (!confirm(`Are you sure you want to delete Floor ${activeFloorIndex + 1}?`)) return;
    }

    const f = floorsData[activeFloorIndex];
    scene.remove(f.floorMesh);
    scene.remove(f.wallsGroup);
    f.wallsGroup.children.forEach(mesh => {
        if (mesh.geometry) mesh.geometry.dispose();
        if (mesh.material) mesh.material.dispose();
    });
    f.roomLabels.forEach(l => { 
        l.element.remove(); 
        scene.remove(l.mesh); 
        if (l.mesh.geometry) l.mesh.geometry.dispose();
        if (l.mesh.material) l.mesh.material.dispose();
    });
    if(f.texture) f.texture.dispose();
    f.floorMesh.geometry.dispose();
    f.floorMesh.material.dispose();

    floorsData.splice(activeFloorIndex, 1);

    floorsData.forEach((floor, idx) => {
        const newYOffset = idx * FLOOR_HEIGHT;
        floor.yOffset = newYOffset;
        floor.floorMesh.position.y = newYOffset;
        floor.wallsGroup.position.y = newYOffset;
        floor.roomLabels.forEach(l => {
            const yStackOffset = 0.05 + ((l.layerIndex || 1) - 1) * 0.8;
            l.mesh.position.y = newYOffset + yStackOffset;
            if (l.center) l.center.y = newYOffset + yStackOffset;
        });
    });

    const deletedIndex = activeFloorIndex;
    activeFloorIndex = Math.max(0, activeFloorIndex - 1);
    
    updateFloorSelector();
    updateFloorVisibility();
    deselectAll();
    
    const userId = document.getElementById('app').dataset.userid || currentUserId;
    if (currentProjectId) {
        try {
            const dbRes = await fetch(`/projects/${userId}`);
            if (dbRes.ok) {
                const dbData = await dbRes.json();
                const proj = dbData.projects.find(p => p.project_id === currentProjectId);
                if (proj && proj.rawBackendData) {
                    proj.rawBackendData.splice(deletedIndex, 1);
                    await fetch(`/projects/save`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            user_id: userId,
                            project_id: currentProjectId,
                            name: proj.name,
                            rawBackendData: proj.rawBackendData
                        })
                    });
                }
            }
        } catch(e) {
            console.error("Failed to sync delete with backend", e);
        }
    }
}

export async function uploadAndAddFloor(file) {
    if (!scene || !renderer) {
        console.log("Auto-recovering 3D Engine after hot-reload...");
        const params = new URLSearchParams(window.location.search);
        const pId = params.get('project_id');
        if (pId) initEngine(pId);
        else return alert("Critical Error: 3D Engine disconnected and no Project ID found.");
    }
    
    const loading = document.getElementById('loading');
    if (loading) {
        loading.style.display = 'flex';
        const p = loading.querySelector('p');
        if (p) p.innerText = "Uploading & Analyzing Floor Plan...";
    }
    
    try {
        const formData = new FormData();
        formData.append('files', file);
        
        const response = await fetch(`/upload`, { method: 'POST', body: formData });
        if (!response.ok) throw new Error("Upload failed");
        const data = await response.json();
        
        if (data.floors && data.floors.length > 0) {
            const floorData = data.floors[0];
            
            const idx = floorsData.length;
            const yOffset = idx * FLOOR_HEIGHT;
            const aspect = floorData.height / floorData.width;
            const floorWidth = 20;
            const floorHeight = 20 * aspect;
            
            const floorGeo = new THREE.PlaneGeometry(floorWidth, floorHeight);
            const floorColor = document.getElementById('floor-color-picker').value || '#e2e8f0';
            const initialFloorOp = parseFloat(document.getElementById('floor-opacity-slider')?.value || "1");
            const floorMat = new THREE.MeshStandardMaterial({ 
                color: floorColor, 
                roughness: 0.8,
                transparent: initialFloorOp < 1,
                opacity: initialFloorOp
            });
            const fMesh = new THREE.Mesh(floorGeo, floorMat);
            fMesh.rotation.x = -Math.PI / 2;
            fMesh.position.y = yOffset;
            fMesh.receiveShadow = true;
            scene.add(fMesh);
        
            const wGroup = new THREE.Group();
            wGroup.position.y = yOffset;
            scene.add(wGroup);
        
            let fMinX = Infinity, fMaxX = -Infinity, fMinZ = Infinity, fMaxZ = -Infinity;
            let fHasWalls = false;
            if (floorData.walls) {
                floorData.walls.forEach(wall => {
                    const pts = wall.points && wall.points.length === 2
                        ? wall.points
                        : (wall.x1 != null ? [{x: wall.x1, z: wall.y1}, {x: wall.x2, z: wall.y2}] : null);
                    if (!pts) return;
                    fHasWalls = true;
                    fMinX = Math.min(fMinX, pts[0].x, pts[1].x);
                    fMaxX = Math.max(fMaxX, pts[0].x, pts[1].x);
                    fMinZ = Math.min(fMinZ, pts[0].z, pts[1].z);
                    fMaxZ = Math.max(fMaxZ, pts[0].z, pts[1].z);
                });
            }
            if (!fHasWalls) {
                fMinX = -10; fMaxX = 10;
                fMinZ = -10 * aspect; fMaxZ = 10 * aspect;
            }

            const newFloor = {
                floorMesh: fMesh,
                wallsGroup: wGroup,
                roomLabels: [],
                yOffset: yOffset,
                imageUrl: floorData.imageUrl,
                texture: null,
                originalWalls: floorData.walls || [],
                bounds: { minX: fMinX, maxX: fMaxX, minZ: fMinZ, maxZ: fMaxZ }
            };
            floorsData.push(newFloor);
            activeFloorIndex = floorsData.length - 1;
            
            if (floorData.imageUrl) {
                const textureLoader = new THREE.TextureLoader();
                const finalUrl = floorData.imageUrl.startsWith('/') ? API_BASE + floorData.imageUrl : floorData.imageUrl;
                textureLoader.load(finalUrl, (texture) => {
                    texture.colorSpace = THREE.SRGBColorSpace;
                    newFloor.texture = texture;
                    if (activeFloorIndex === floorsData.indexOf(newFloor) && document.getElementById('show-blueprint').checked) {
                        fMesh.material.map = texture;
                        fMesh.material.color.setHex(0xffffff);
                        fMesh.material.needsUpdate = true;
                    }
                });
            }
            
            if (floorData.walls) {
                floorData.walls.forEach(wall => {
                    const pts = wall.points && wall.points.length === 2
                        ? wall.points
                        : (wall.x1 != null ? [{x: wall.x1, z: wall.y1}, {x: wall.x2, z: wall.y2}] : null);
                    if (!pts) return;
                    const start = new THREE.Vector3(pts[0].x, 0, pts[0].z);
                    const end = new THREE.Vector3(pts[1].x, 0, pts[1].z);
                    createManualWall(start, end, newFloor);
                });
            }
            
            if (floorData.rooms) {
                floorData.rooms.forEach(room => {
                    const pos = new THREE.Vector3(room.x, yOffset, room.z);
                    if (room.polygon && room.polygon.length >= 3) {
                        createPolygonRoom(room, newFloor, yOffset);
                    } else {
                        createNewRoomMarker(pos, room.name, false, newFloor, room.w || 2, room.h || 2, true, false, room);
                    }
                });
            }

            const selector = document.getElementById('floor-selector');
            const opt = document.createElement('option');
            opt.value = activeFloorIndex;
            opt.innerText = `Floor ${activeFloorIndex + 1}`;
            selector.appendChild(opt);
            selector.value = activeFloorIndex;
            
            updateFloorVisibility();
            deselectAll();
            
            const userId = document.getElementById('app').dataset.userid || currentUserId;
            if (currentProjectId) {
                const dbRes = await fetch(`/projects/${userId}`);
                if (dbRes.ok) {
                    const dbData = await dbRes.json();
                    const proj = dbData.projects.find(p => p.project_id === currentProjectId);
                    if (proj) {
                        const updatedRawData = proj.rawBackendData || [];
                        updatedRawData.push(floorData);
                        await fetch(`/projects/save`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                user_id: userId,
                                project_id: currentProjectId,
                                name: proj.name,
                                rawBackendData: updatedRawData
                            })
                        });
                    }
                }
            }
        }
    } catch(e) {
        console.error("Upload error details:", e);
        alert("Failed to upload new floor: " + e.message + "\n\nSee console for details.");
    } finally {
        if (loading) {
            loading.style.display = 'none';
            const p = loading.querySelector('p');
            if (p) p.innerText = "Generating 3D Model...";
        }
    }
}

function getIntersects(event, objects) {
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    return raycaster.intersectObjects(objects, true);
}

function onMouseMove(event) {
    const activeFloor = getActiveFloor();
    if (!activeFloor) return;
    
    if (isDrawingFloor && floorDrawStartPoint) {
        const hits = getIntersects(event, [activeFloor.floorMesh]);
        if (hits.length > 0) {
            const currentY = activeFloor.floorMesh.position.y;
            const endPoint = hits[0].point.clone();
            endPoint.y -= currentY;
            
            const width = Math.abs(endPoint.x - floorDrawStartPoint.x);
            const depth = Math.abs(endPoint.z - floorDrawStartPoint.z);
            const centerX = (endPoint.x + floorDrawStartPoint.x) / 2;
            const centerZ = (endPoint.z + floorDrawStartPoint.z) / 2;
            
            if (width > 0 && depth > 0) {
                if (!floorDrawPreview) {
                    const geo = new THREE.PlaneGeometry(width, depth);
                    const mat = new THREE.MeshBasicMaterial({ color: 0xe84393, transparent: true, opacity: 0.5, side: THREE.DoubleSide });
                    floorDrawPreview = new THREE.Mesh(geo, mat);
                    floorDrawPreview.rotation.x = -Math.PI / 2;
                    floorDrawPreview.position.set(centerX, currentY + 0.05, centerZ);
                    scene.add(floorDrawPreview);
                } else {
                    floorDrawPreview.geometry.dispose();
                    floorDrawPreview.geometry = new THREE.PlaneGeometry(width, depth);
                    floorDrawPreview.position.set(centerX, currentY + 0.05, centerZ);
                }
            }
        }
        return;
    }
    
    if (!isDrawingWall || !drawStartPoint) return;
    
    const hits = getIntersects(event, [activeFloor.floorMesh]);
    if (hits.length > 0) {
        let endPoint = hits[0].point;
        const currentY = activeFloor.floorMesh.position.y;
        endPoint.y -= currentY;
        
        const dx = endPoint.x - drawStartPoint.x;
        const dz = endPoint.z - drawStartPoint.z;
        const angle = Math.atan2(dz, dx);
        const snapAngle = Math.PI / 8; 
        const absAngle = Math.abs(angle);
        
        if (absAngle < snapAngle || absAngle > Math.PI - snapAngle) {
            endPoint.z = drawStartPoint.z; 
        } else if (Math.abs(absAngle - Math.PI/2) < snapAngle) {
            endPoint.x = drawStartPoint.x; 
        }
        
        const globalStart = drawStartPoint.clone();
        globalStart.y += currentY;
        const globalEnd = endPoint.clone();
        globalEnd.y += currentY;

        if (!drawPreviewLine) {
            const mat = new THREE.LineBasicMaterial({ color: 0x00b894, linewidth: 2 });
            const geo = new THREE.BufferGeometry().setFromPoints([globalStart, globalEnd]);
            drawPreviewLine = new THREE.Line(geo, mat);
            drawPreviewLine.position.y = currentY + 0.1;
            scene.add(drawPreviewLine);
        } else {
            drawPreviewLine.geometry.setFromPoints([globalStart, globalEnd]);
            drawPreviewLine.position.y = currentY + 0.1;
        }
    }
}

function onClick(event) {
    const activeFloor = getActiveFloor();
    if (!activeFloor) return;

    if (isDrawingFloor) {
        const hits = getIntersects(event, [activeFloor.floorMesh]);
        if (hits.length > 0) {
            const currentY = activeFloor.floorMesh.position.y;
            if (!floorDrawStartPoint) {
                floorDrawStartPoint = hits[0].point.clone();
                floorDrawStartPoint.y -= currentY;
                const drawFloorBtn = document.getElementById('draw-floor-btn');
                drawFloorBtn.innerText = 'Draw Room Floor';
            } else {
                const endPoint = hits[0].point.clone();
                endPoint.y -= currentY;
                
                const width = Math.abs(endPoint.x - floorDrawStartPoint.x);
                const depth = Math.abs(endPoint.z - floorDrawStartPoint.z);
                const centerX = (endPoint.x + floorDrawStartPoint.x) / 2;
                const centerZ = (endPoint.z + floorDrawStartPoint.z) / 2;
                
                if (width > 0.5 && depth > 0.5) {
                    const pos = new THREE.Vector3(centerX, currentY, centerZ);
                    createNewRoomMarker(pos, '', true, activeFloor, width, depth);
                }
                
                isDrawingFloor = false;
                floorDrawStartPoint = null;
                if(floorDrawPreview) { scene.remove(floorDrawPreview); floorDrawPreview.geometry.dispose(); if(floorDrawPreview.material) floorDrawPreview.material.dispose(); floorDrawPreview = null; }
                const drawFloorBtn = document.getElementById('draw-floor-btn');
                drawFloorBtn.style.background = '#e84393';
                drawFloorBtn.innerText = 'Draw Room Floor';
            }
        }
        return;
    }

    if (isDrawingWall) {
        const hits = getIntersects(event, [activeFloor.floorMesh]);
        if (hits.length > 0) {
            const currentY = activeFloor.floorMesh.position.y;
            if (!drawStartPoint) {
                drawStartPoint = hits[0].point.clone();
                drawStartPoint.y -= currentY;
            } else {
                let drawEndPoint = hits[0].point.clone();
                drawEndPoint.y -= currentY;
                
                const dx = drawEndPoint.x - drawStartPoint.x;
                const dz = drawEndPoint.z - drawStartPoint.z;
                const angle = Math.atan2(dz, dx);
                const snapAngle = Math.PI / 8; 
                const absAngle = Math.abs(angle);
                
                if (absAngle < snapAngle || absAngle > Math.PI - snapAngle) {
                    drawEndPoint.z = drawStartPoint.z;
                } else if (Math.abs(absAngle - Math.PI/2) < snapAngle) {
                    drawEndPoint.x = drawStartPoint.x;
                }
                
                if (drawStartPoint.distanceTo(drawEndPoint) > 0.1) {
                    createManualWall(drawStartPoint, drawEndPoint, activeFloor);
                }
                
                isDrawingWall = false;
                drawStartPoint = null;
                if(drawPreviewLine) { scene.remove(drawPreviewLine); if(drawPreviewLine.geometry) drawPreviewLine.geometry.dispose(); if(drawPreviewLine.material) drawPreviewLine.material.dispose(); drawPreviewLine = null; }
                const drawBtn = document.getElementById('draw-wall-btn');
                if(drawBtn) drawBtn.style.background = 'var(--accent)';
                if(drawBtn) drawBtn.innerText = 'Draw Wall';
            }
        }
        return;
    }

    const targets = [];
    if (document.getElementById('stack-floors-mode').checked) {
        floorsData.forEach(f => {
            targets.push(f.floorMesh);
            targets.push(...f.wallsGroup.children);
            targets.push(...f.roomLabels.map(l => l.mesh));
        });
        targets.push(...pillarsGroup.children);
    } else {
        targets.push(activeFloor.floorMesh);
        targets.push(...activeFloor.wallsGroup.children);
        targets.push(...activeFloor.roomLabels.map(l => l.mesh));
    }
    
    const intersects = getIntersects(event, targets);

    if (intersects.length > 0) {
        const hit = intersects[0];
        deselectAll();

        let hitFloor = null;
        floorsData.forEach(f => {
            if (f.floorMesh === hit.object || f.wallsGroup.children.includes(hit.object) || f.roomLabels.some(l => l.mesh === hit.object)) {
                hitFloor = f;
            }
        });

        if (hitFloor && hitFloor !== activeFloor) {
            document.getElementById('floor-selector').value = floorsData.indexOf(hitFloor);
            updateFloorSelector();
            updateFloorVisibility();
        }
        
        const currentActiveFloor = hitFloor || activeFloor;

        if (currentActiveFloor.wallsGroup.children.includes(hit.object) || pillarsGroup.children.includes(hit.object)) {
            selectWall(hit.object);
        } else if (hit.object === currentActiveFloor.floorMesh && isAddingRoom) {
            const currentY = currentActiveFloor.floorMesh.position.y;
            const pos = hit.point.clone();
            pos.y = currentY + 0.05;
            createNewRoomMarker(pos, '', true, currentActiveFloor);
            
            isAddingRoom = false;
        } else if (hit.object !== currentActiveFloor.floorMesh) {
            const label = currentActiveFloor.roomLabels.find(l => l.mesh === hit.object);
            if (label) selectRoom(label);
        }
    }
}

function createPolygonRoom(room, floorData, elevation) {
    const shape = new THREE.Shape();
    const pts = room.polygon;
    shape.moveTo(pts[0].x, -pts[0].z);
    for(let i=1; i<pts.length; i++) {
        shape.lineTo(pts[i].x, -pts[i].z);
    }
    shape.lineTo(pts[0].x, -pts[0].z);
    
    const geo = new THREE.ShapeGeometry(shape);
    
    let autoColor = 0x3498db; // Default blue
    const lowerName = (room.name || '').toLowerCase();
    if (lowerName.includes('bed')) autoColor = 0x2ecc71;
    else if (lowerName.includes('bath') || lowerName.includes('wc') || lowerName.includes('toilet')) autoColor = 0x00a8ff;
    else if (lowerName.includes('dining') || lowerName.includes('kitchen')) autoColor = 0xe74c3c;
    else if (lowerName.includes('passage') || lowerName.includes('hall') || lowerName.includes('corridor')) autoColor = 0xff9ff3;
    else if (/\d/.test(lowerName)) autoColor = 0xf1c40f;
    
    const initialFloorOp = parseFloat(document.getElementById('floor-opacity-slider')?.value || "1");
    const groupId = room.groupId || 'grp_' + Math.random().toString(36).substr(2, 9);
    
    let layersDef = (room.layers && room.layers.length === 3) ? room.layers : null;
    if (layersDef) {
        // Fix legacy projects where layers 2 and 3 were saved as pure white
        if (layersDef[1].color === '#ffffff') layersDef[1].color = '#' + new THREE.Color(`hsl(${Math.floor(Math.random()*360)}, 70%, 60%)`).getHexString();
        if (layersDef[2].color === '#ffffff') layersDef[2].color = '#' + new THREE.Color(`hsl(${Math.floor(Math.random()*360)}, 70%, 60%)`).getHexString();
    } else {
        layersDef = [
            { name: (room.layerNames && room.layerNames[0] !== undefined) ? room.layerNames[0] : (room.name || ''), layerIndex: 1, color: room.color || '#' + new THREE.Color(autoColor).getHexString() },
            { name: (room.layerNames && room.layerNames[1] !== undefined) ? room.layerNames[1] : '', layerIndex: 2, color: '#' + new THREE.Color(`hsl(${Math.floor(Math.random()*360)}, 70%, 60%)`).getHexString() },
            { name: (room.layerNames && room.layerNames[2] !== undefined) ? room.layerNames[2] : '', layerIndex: 3, color: '#' + new THREE.Color(`hsl(${Math.floor(Math.random()*360)}, 70%, 60%)`).getHexString() }
        ];
    }
    
    layersDef.forEach(layerDef => {
        const mat = new THREE.MeshStandardMaterial({ 
            color: new THREE.Color(layerDef.color).getHex(), 
            transparent: initialFloorOp < 1, 
            opacity: initialFloorOp, 
            side: THREE.DoubleSide 
        });
        
        // Increased vertical gap to prevent Z-fighting with the blueprint floor
        const yStackOffset = 0.1 + (layerDef.layerIndex - 1) * 0.8;
        
        const mesh = new THREE.Mesh(geo, mat);
        mesh.rotation.x = -Math.PI / 2;
        mesh.position.y = elevation + yStackOffset;
        
        // Add black borders to every single tile
        const edges = new THREE.EdgesGeometry(geo);
        const line = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({ color: 0x000000 }));
        mesh.add(line);
        
        scene.add(mesh);
        
        const div = document.createElement('div');
        div.className = 'room-label';
        div.innerText = layerDef.name || '';
        div.style.display = layerDef.name ? 'block' : 'none';
        document.getElementById('labels-container').appendChild(div);
        
        const labelCenter = new THREE.Vector3(room.x, elevation + yStackOffset, room.z);
        const roomLabel = { 
            mesh: mesh, 
            element: div, 
            name: layerDef.name, 
            layerIndex: layerDef.layerIndex, 
            groupId: groupId,
            color: layerDef.color, 
            center: labelCenter, 
            polygon: room.polygon, 
            w: room.w, 
            h: room.h 
        };
        floorData.roomLabels.push(roomLabel);
    });
}

function createManualWall(start, end, floorData) {
    const height   = FLOOR_HEIGHT - 0.02;
    const distance = start.distanceTo(end);
    const pSize    = 0.3;

    // No inner walls or inner pillars are drawn as requested.
    // The wall object creation is bypassed.
}

export function toggleWallMode() {
    wallMode = wallMode === 'pillars' ? 'walls' : 'pillars';
    floorsData.forEach(f => {
        f.wallsGroup.children.forEach(mesh => {
            if (mesh.userData.wallType === 'full')   mesh.visible = (wallMode === 'walls');
            if (mesh.userData.wallType === 'pillar') mesh.visible = (wallMode === 'pillars');
        });
    });
    return wallMode;
}

function deselectAll() {
    if (selectedWall) {
        selectedWall.material = wallMat.clone();
        selectedWall = null;
    }
    selectedRoomLabel = null;
    document.getElementById('selection-details').style.display = 'none';
    document.getElementById('no-selection').style.display = 'block';
    document.getElementById('delete-btn').style.display = 'none';
    window.isolatedRoomGroupId = null;
    window.isolatedLayerIndex = null;
    const tf = document.getElementById('tile-layer-filter-container');
    if (tf) tf.style.display = 'none';
}

function selectWall(mesh) {
    selectedWall = mesh;
    mesh.material = wallSelectedMat.clone();
    
    document.getElementById('delete-btn').style.display = 'flex';
    document.getElementById('delete-btn').innerText = 'Delete Wall';
    document.getElementById('no-selection').style.display = 'block';
    document.getElementById('no-selection').innerText = 'Wall selected. Use Arrow Keys to move it, or delete it.';
}

function createNewRoomMarker(position, initialName = '', autoSelect = true, floorData, w=2, h=2, isAutomatic=false, hideTile=false, roomObj=null) {
    const geo = new THREE.PlaneGeometry(w, h);
    
    let autoColor = 0x3498db;
    if (isAutomatic) {
        const lowerName = initialName.toLowerCase();
        if (lowerName.includes('bed')) autoColor = 0x2ecc71;
        else if (lowerName.includes('bath') || lowerName.includes('toilet') || lowerName.includes('wc')) autoColor = 0x00a8ff;
        else if (lowerName.includes('dining')) autoColor = 0xe74c3c;
        else if (lowerName.includes('passage') || lowerName.includes('hall') || lowerName.includes('corridor')) autoColor = 0xff9ff3;
        else if (/\d/.test(lowerName) && (/[xX\'\"*]/.test(lowerName) || lowerName.includes('sq') || lowerName.includes('ft') || lowerName.includes('m2'))) autoColor = 0xf1c40f;
    } else {
        const hue = Math.floor(Math.random() * 360);
        autoColor = new THREE.Color(`hsl(${hue}, 70%, 60%)`).getHex();
    }
    
    const baseColor = (roomObj && roomObj.color) ? roomObj.color : '#' + new THREE.Color(autoColor).getHexString();
    
    const groupId = (roomObj && roomObj.groupId) ? roomObj.groupId : 'grp_' + Math.random().toString(36).substr(2, 9);
    
    let layersDef = (roomObj && roomObj.layers && roomObj.layers.length === 3) ? roomObj.layers : null;
    if (layersDef) {
        if (layersDef[1].color === '#ffffff') layersDef[1].color = '#' + new THREE.Color(`hsl(${Math.floor(Math.random()*360)}, 70%, 60%)`).getHexString();
        if (layersDef[2].color === '#ffffff') layersDef[2].color = '#' + new THREE.Color(`hsl(${Math.floor(Math.random()*360)}, 70%, 60%)`).getHexString();
    } else {
        layersDef = [
            { name: (roomObj && roomObj.layerNames && roomObj.layerNames[0] !== undefined) ? roomObj.layerNames[0] : initialName, layerIndex: 1, color: baseColor },
            { name: (roomObj && roomObj.layerNames && roomObj.layerNames[1] !== undefined) ? roomObj.layerNames[1] : '', layerIndex: 2, color: '#' + new THREE.Color(`hsl(${Math.floor(Math.random()*360)}, 70%, 60%)`).getHexString() },
            { name: (roomObj && roomObj.layerNames && roomObj.layerNames[2] !== undefined) ? roomObj.layerNames[2] : '', layerIndex: 3, color: '#' + new THREE.Color(`hsl(${Math.floor(Math.random()*360)}, 70%, 60%)`).getHexString() }
        ];
    }
    
    const initialFloorOp = parseFloat(document.getElementById('floor-opacity-slider')?.value || "1");
    let primaryRoomLabel = null;
    
    layersDef.forEach(layerDef => {
        let mat;
        if (isAutomatic) {
            mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(layerDef.color).getHex(), transparent: true, opacity: hideTile ? 0.0 : 0.6 });
        } else {
            mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(layerDef.color).getHex(), transparent: initialFloorOp < 1, opacity: initialFloorOp });
        }
        
        // Increased vertical gap to 0.8 units between layers to create floating shelves effect
        const yStackOffset = 0.05 + (layerDef.layerIndex - 1) * 0.8;
        
        const mesh = new THREE.Mesh(geo, mat);
        mesh.rotation.x = -Math.PI / 2;
        mesh.position.copy(position);
        mesh.position.y += yStackOffset;
        
        // Add black borders to every single tile
        const edges = new THREE.EdgesGeometry(geo);
        const line = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({ color: 0x000000 }));
        mesh.add(line);
        
        scene.add(mesh);

        const div = document.createElement('div');
        div.className = 'room-label';
        div.innerText = layerDef.name;
        div.style.display = layerDef.name.trim() ? 'block' : 'none';
        document.getElementById('labels-container').appendChild(div);

        const roomLabel = { 
            mesh: mesh, 
            element: div, 
            name: layerDef.name, 
            layerIndex: layerDef.layerIndex,
            groupId: groupId,
            color: layerDef.color, 
            w: w, 
            h: h 
        };
        floorData.roomLabels.push(roomLabel);
        
        if (layerDef.layerIndex === 1) {
            primaryRoomLabel = roomLabel;
        }
    });
    
    if (autoSelect && primaryRoomLabel) {
        selectRoom(primaryRoomLabel);
    }
}

function selectRoom(labelObj) {
    selectedRoomLabel = labelObj;
    document.getElementById('no-selection').style.display = 'none';
    document.getElementById('selection-details').style.display = 'block';
    document.getElementById('room-name-input').value = labelObj.name;
    document.getElementById('room-color-picker').value = '#' + labelObj.mesh.material.color.getHexString();
    
    document.getElementById('delete-btn').style.display = 'flex';
    document.getElementById('delete-btn').innerText = 'Delete Floor / Marker';
    
    window.isolatedRoomGroupId = labelObj.groupId;
    window.isolatedLayerIndex = null;
    
    const tf = document.getElementById('tile-layer-filter-container');
    const btns = document.getElementById('tile-layer-buttons');
    if (tf && btns) {
        btns.innerHTML = '';
        tf.style.display = 'block';
        
        const f = floorsData[activeFloorIndex];
        if (f) {
            const layers = f.roomLabels.filter(l => l.groupId === labelObj.groupId).sort((a,b) => (a.layerIndex||1) - (b.layerIndex||1));
            
            const allBtn = document.createElement('button');
            allBtn.innerText = 'Show All Layers';
            allBtn.className = 'tool-btn';
            allBtn.style.background = 'var(--accent)';
            allBtn.style.border = '2px solid #fff';
            allBtn.onclick = () => {
                window.isolatedLayerIndex = null;
                Array.from(btns.children).forEach(b => b.style.border = 'none');
                allBtn.style.border = '2px solid #fff';
            };
            btns.appendChild(allBtn);
            
            layers.forEach(l => {
                const btn = document.createElement('button');
                btn.id = `iso-btn-${l.layerIndex}`;
                btn.innerText = `Layer ${l.layerIndex}: ${l.name || 'Unnamed'}`;
                btn.className = 'tool-btn';
                btn.style.background = 'var(--bg-secondary)';
                btn.onclick = () => {
                    window.isolatedLayerIndex = l.layerIndex;
                    Array.from(btns.children).forEach(b => b.style.border = 'none');
                    btn.style.border = '2px solid var(--accent)';
                    
                    selectedRoomLabel = l;
                    document.getElementById('room-name-input').value = l.name || '';
                    document.getElementById('room-color-picker').value = '#' + l.mesh.material.color.getHexString();
                };
                btns.appendChild(btn);
            });
        }
    }
}

function updateLabels() {
    const showLabels = document.getElementById('show-room-labels')?.checked ?? true;
    const showL1 = document.getElementById('show-layer-1')?.checked ?? true;
    const showL2 = document.getElementById('show-layer-2')?.checked ?? true;
    const showL3 = document.getElementById('show-layer-3')?.checked ?? true;

    floorsData.forEach((f, idx) => {
        f.roomLabels.forEach(label => {
            // Set mesh visibility based on layerIndex AND floor visibility
            const lIdx = label.layerIndex || 1;
            if (!f.isVisible) {
                label.mesh.visible = false;
            } else {
                let defaultVisible = false;
                if (lIdx === 1) defaultVisible = showL1;
                else if (lIdx === 2) defaultVisible = showL2;
                else if (lIdx === 3) defaultVisible = showL3;
                
                if (window.isolatedRoomGroupId && label.groupId === window.isolatedRoomGroupId) {
                    if (window.isolatedLayerIndex !== null) {
                        label.mesh.visible = (lIdx === window.isolatedLayerIndex);
                    } else {
                        label.mesh.visible = defaultVisible;
                    }
                } else {
                    label.mesh.visible = defaultVisible;
                }
            }

            if (!showLabels || !f.isVisible || !label.mesh.visible || hiddenLabelFloors.has(idx) || !label.element || !label.name.trim()) {
                if (label.element) label.element.style.display = 'none';
                return;
            }

            const vector = new THREE.Vector3();
            if (label.center) {
                vector.copy(label.center);
            } else {
                vector.setFromMatrixPosition(label.mesh.matrixWorld);
            }
            vector.project(camera);

            const rect = renderer.domElement.getBoundingClientRect();
            const x = (vector.x * .5 + .5) * rect.width;
            const y = (vector.y * -.5 + .5) * rect.height;

            if (vector.z > 1.0) {
                if (label.element.style.display !== 'none') label.element.style.display = 'none';
            } else {
                if (label.element.style.display !== 'block') label.element.style.display = 'block';
                const px = `${x.toFixed(1)}px`;
                const py = `${y.toFixed(1)}px`;
                if (label.element.style.left !== px) label.element.style.left = px;
                if (label.element.style.top !== py) label.element.style.top = py;
            }
        });
    });
}

function onWindowResize() {
    const container = document.getElementById('canvas-container');
    if (!container || !camera || !renderer) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
}

function animate() {
    animationFrameId = requestAnimationFrame(animate);
    if (controls) controls.update();
    if (scene && camera && renderer) {
        updateLabels();
        renderer.render(scene, camera);
    }
}

