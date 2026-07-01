import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { initEngine, cleanupEngine, uploadAndAddFloor, toggleFloorLabels, isFloorLabelsVisible, toggleWallMode, saveCurrentProject } from '../engine/engine';

function Editor() {
  const [projectId, setProjectId] = useState(null);
  const [showLabels, setShowLabels] = useState(true);
  const [currentFloorLabelsVisible, setCurrentFloorLabelsVisible] = useState(true);
  const [wallMode, setWallMode] = useState('pillars');
  const location = useLocation();
  const navigate = useNavigate();

  const handleLabelsToggle = (e) => {
    setShowLabels(e.target.checked);
    // engine's updateLabels() reads #show-room-labels checkbox each frame
  };

  const handleFloorLabelsToggle = () => {
    const selector = document.getElementById('floor-selector');
    const idx = selector ? selector.selectedIndex : 0;
    const nowVisible = toggleFloorLabels(idx);
    setCurrentFloorLabelsVisible(nowVisible);
  };

  const handleFloorChange = () => {
    const selector = document.getElementById('floor-selector');
    const idx = selector ? selector.selectedIndex : 0;
    setCurrentFloorLabelsVisible(isFloorLabelsVisible(idx));
  };

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const pId = params.get('project_id');
    if (!pId) {
      navigate('/dashboard');
      return;
    }
    setProjectId(pId);
  }, [location, navigate]);

  useEffect(() => {
    if (projectId) {
      initEngine(projectId);
    }
    return () => {
      cleanupEngine();
    };
  }, [projectId]);

  const userId = localStorage.getItem('user_id');

  return (
    <div id="app" className="screen workspace-layout" data-userid={userId}>
      
      {/* Top Toolbar */}
      <div id="top-toolbar" className="workspace-header">
        <div className="logo" style={{display:'flex', alignItems:'center', gap:10}}>
          <h1 id="btn-back-dashboard" onClick={() => navigate('/dashboard')} style={{cursor: 'pointer'}} title="Back to Dashboard">ArchTransform</h1>
          <button
            onClick={async () => {
              await saveCurrentProject();
              navigate(`/annotate?project_id=${projectId}`);
            }}
            title="Back to Room Annotation"
            style={{
              display:'flex', alignItems:'center', gap:5,
              background:'transparent', border:'1px solid var(--border)',
              color:'var(--text-muted)', cursor:'pointer',
              fontSize:12, fontWeight:500, padding:'4px 10px', borderRadius:6,
              transition:'all 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor='var(--accent)'; e.currentTarget.style.color='var(--accent)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor='var(--border)'; e.currentTarget.style.color='var(--text-muted)'; }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="15 18 9 12 15 6"/></svg>
            Annotation
          </button>
        </div>
        
        <div className="global-controls" id="multi-floor-controls">
          <div className="floor-actions">
            <span className="toolbar-label">Floor:</span>
            <select id="floor-selector" className="toolbar-select" onChange={handleFloorChange}></select>
            <button
              onClick={handleFloorLabelsToggle}
              title={currentFloorLabelsVisible ? 'Hide this floor\'s labels' : 'Show this floor\'s labels'}
              className="toolbar-btn"
              style={{
                width: 28, padding: 0,
                color: currentFloorLabelsVisible ? 'var(--accent)' : '#A3A3A3',
                background: currentFloorLabelsVisible ? 'rgba(197,134,86,0.08)' : 'transparent',
                border: 'none',
              }}
            >
              {currentFloorLabelsVisible
                ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
              }
            </button>
          </div>
          <div className="toolbar-divider"></div>
          <label className="toolbar-checkbox">
            <input type="checkbox" id="stack-floors-mode" /> Stacked View
          </label>
          <label className="toolbar-checkbox">
            <input type="checkbox" id="show-blueprint" defaultChecked /> Blueprint
          </label>
          <label className="toolbar-checkbox">
            <input type="checkbox" id="show-room-labels" checked={showLabels} onChange={handleLabelsToggle} /> Room Labels
          </label>
          <div className="toolbar-divider"></div>

        </div>

        <button id="save-project-btn" className="save-btn">
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
  </svg>
  Save
</button>
      </div>

      <div className="workspace-body">
        
        {/* Left Tools Panel */}
        <div id="left-tools-panel">


          <div className="lp-section-label">Rooms</div>
          <div className="tools-group" id="room-controls-tools">
            <button id="draw-floor-btn" className="tool-btn pink-tool" title="Draw Room Floor">
              <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><path d="M3 9h18M9 21V9"/></svg>
              Draw Floor
            </button>
          </div>

          <div className="tools-divider"></div>

          <div className="lp-section-label">Layer Filters</div>
          <div className="tools-group">
            <label className="toolbar-checkbox" style={{display: 'flex', alignItems: 'center', gap: '8px', padding: '8px', background: 'var(--bg-secondary)', borderRadius: '6px', cursor: 'pointer'}}>
              <input type="checkbox" id="show-layer-1" defaultChecked /> 
              <span style={{fontSize: '13px', color: 'var(--text)'}}>Layer 1 (Base)</span>
            </label>
            <label className="toolbar-checkbox" style={{display: 'flex', alignItems: 'center', gap: '8px', padding: '8px', background: 'var(--bg-secondary)', borderRadius: '6px', marginTop: '4px', cursor: 'pointer'}}>
              <input type="checkbox" id="show-layer-2" defaultChecked /> 
              <span style={{fontSize: '13px', color: 'var(--text)'}}>Layer 2</span>
            </label>
            <label className="toolbar-checkbox" style={{display: 'flex', alignItems: 'center', gap: '8px', padding: '8px', background: 'var(--bg-secondary)', borderRadius: '6px', marginTop: '4px', cursor: 'pointer'}}>
              <input type="checkbox" id="show-layer-3" defaultChecked /> 
              <span style={{fontSize: '13px', color: 'var(--text)'}}>Layer 3</span>
            </label>
          </div>
          
          <div id="tile-layer-filter-container" style={{display: 'none', marginTop: '15px', background: 'var(--bg-primary)', padding: '10px', borderRadius: '6px', border: '1px solid var(--border)'}}>
            <div style={{fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '8px'}}>Isolate Layer</div>
            <div style={{display: 'flex', flexDirection: 'column', gap: '6px'}} id="tile-layer-buttons">
                {/* Buttons will be dynamically injected here */}
            </div>
          </div>

          {/* Spacer pushes delete to bottom */}
          <div style={{ flex: 1 }} />

          {/* Contextual delete action — engine shows/hides this */}
          <div className="lp-delete-zone">
            <button id="delete-btn" className="tool-btn-delete" title="Delete Selected">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
              Delete
            </button>
          </div>
        </div>

        {/* Central Viewport */}
        <div id="viewer-container" className="workspace-viewport">
          <div id="canvas-container"></div>
          <div id="labels-container"></div>
          <div className="loading-overlay" id="loading" style={{display: 'none'}}>
            <div className="spinner"></div>
            <p>Processing Architectural Data...</p>
          </div>
        </div>

        {/* Right Properties Panel */}
        <div id="right-properties-panel" className="controls-section">
          <div className="prop-header">Properties</div>
          
          <div className="prop-group">
            <label>Scene Background</label>
            <div className="color-picker-wrapper">
              <input type="color" id="bg-color-picker" defaultValue="#f1f5f9" />
            </div>
          </div>

          <div className="prop-group" id="floor-settings">
            <label>Default Floor Color</label>
            <div className="color-picker-wrapper">
              <input type="color" id="floor-color-picker" defaultValue="#e2e8f0" />
            </div>
            <div style={{marginTop: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
              <label style={{margin: 0}}>Floor Opacity</label>
              <span id="floor-opacity-val" style={{fontSize: '12px', color: '#64748b', fontWeight: 'bold'}}>100%</span>
            </div>
            <input type="range" id="floor-opacity-slider" min="0.1" max="1" step="0.1" defaultValue="1" style={{width: '100%', marginTop: '8px', cursor: 'pointer', accentColor: 'var(--accent)'}} />
            <label style={{marginTop: '12px'}}>Wall Color</label>
            <div className="color-picker-wrapper">
              <input type="color" id="wall-color-picker" defaultValue="#94a3b8" />
            </div>
            <div style={{marginTop: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
              <label style={{margin: 0}}>Wall Opacity</label>
              <span id="wall-opacity-val" style={{fontSize: '12px', color: '#64748b', fontWeight: 'bold'}}>100%</span>
            </div>
            <input type="range" id="wall-opacity-slider" min="0.1" max="1" step="0.1" defaultValue="1" style={{width: '100%', marginTop: '8px', cursor: 'pointer', accentColor: 'var(--accent)'}} />
          </div>

          <div className="prop-group" id="room-controls">
            <div className="prop-sub-header">Selection</div>
            <p id="no-selection" className="info-text">No object selected.<br/><br/>Click a floor or wall in the canvas to edit its properties.</p>
            
            <div id="selection-details" style={{display: 'none'}}>
              <label>Room Name</label>
              <input type="text" id="room-name-input" className="prop-input" placeholder="e.g., Living Room" />
              <label style={{marginTop: '12px'}}>Floor Color</label>
              <div className="color-picker-wrapper">
                <input type="color" id="room-color-picker" defaultValue="#ffffff" />
              </div>
              <p className="hint-text"><b>Hint:</b> Use Arrow Keys to move, Shift+Arrow to resize.</p>
            </div>
          </div>
        </div>

      </div>
      
      {/* Delete Confirmation Modal */}
      <div id="delete-confirm-modal" className="modal-overlay" style={{display: 'none', zIndex: 1000}}>
        <div className="modal-card">
          <div className="modal-icon warning">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          </div>
          <h3 id="delete-modal-title">Delete Floor?</h3>
          <p>This action is completely permanent and cannot be undone.</p>
          <div className="modal-actions">
            <button id="btn-cancel-delete" className="modal-btn secondary">Cancel</button>
            <button id="btn-confirm-delete" className="modal-btn danger">Delete Floor</button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Editor;
