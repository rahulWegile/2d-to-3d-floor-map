import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchApi, fetchApiForm, fetchSSEForm, removeToken } from '../api';

/* ─────────────────────────────────────────────────────────────
   Sub-components
───────────────────────────────────────────────────────────── */

function ProjectCard({ name, floors, onClick, onDelete, onRename }) {
  const [hovered, setHovered] = useState(false);
  const [deleteHovered, setDeleteHovered] = useState(false);
  const [renameHovered, setRenameHovered] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const handleDeleteClick = (e) => { e.stopPropagation(); setConfirming(true); };
  const handleRenameClick = (e) => { e.stopPropagation(); onRename(); };
  const handleConfirm = (e) => { e.stopPropagation(); onDelete(); };
  const handleCancel = (e) => { e.stopPropagation(); setConfirming(false); };

  return (
    <div
      onClick={confirming ? undefined : onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setConfirming(false); }}
      style={{
        background: '#FFFFFF',
        border: `1px solid ${hovered ? '#E2C4A2' : '#EBEBEB'}`,
        borderRadius: '12px',
        padding: '22px 22px 18px',
        cursor: confirming ? 'default' : 'pointer',
        transition: 'border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: hovered
          ? '0 6px 24px rgba(197, 134, 86, 0.1)'
          : '0 1px 3px rgba(0,0,0,0.04)',
        transform: hovered ? 'translateY(-2px)' : 'none',
      }}
    >
      {/* Action buttons (top-right, visible on hover) */}
      {hovered && !confirming && (
        <div style={{ position: 'absolute', top: '12px', right: '12px', display: 'flex', gap: '6px' }}>
          {/* Rename */}
          <button
            onClick={handleRenameClick}
            onMouseEnter={() => setRenameHovered(true)}
            onMouseLeave={() => setRenameHovered(false)}
            title="Rename"
            style={{
              width: '28px', height: '28px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: renameHovered ? '#F0F9FF' : '#F5F5F4',
              border: `1px solid ${renameHovered ? '#BAE6FD' : '#E5E5E5'}`,
              borderRadius: '7px', cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
              stroke={renameHovered ? '#0284C7' : '#A3A3A3'}
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </button>
          {/* Delete */}
          <button
            onClick={handleDeleteClick}
            onMouseEnter={() => setDeleteHovered(true)}
            onMouseLeave={() => setDeleteHovered(false)}
            title="Delete"
            style={{
              width: '28px', height: '28px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: deleteHovered ? '#FEF2F2' : '#F5F5F4',
              border: `1px solid ${deleteHovered ? '#FECACA' : '#E5E5E5'}`,
              borderRadius: '7px', cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
              stroke={deleteHovered ? '#DC2626' : '#A3A3A3'}
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
              <path d="M10 11v6M14 11v6"/>
              <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
            </svg>
          </button>
        </div>
      )}

      {/* Confirm delete overlay */}
      {confirming && (
        <div style={{
          position: 'absolute', inset: 0,
          background: 'rgba(255,255,255,0.95)',
          borderRadius: '12px',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          gap: '12px', zIndex: 2,
        }}>
          <p style={{ fontSize: '13px', fontWeight: '600', color: '#1A1A1A', textAlign: 'center', padding: '0 12px' }}>
            Delete "{name}"?
          </p>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button onClick={handleConfirm} style={{
              padding: '7px 14px', background: '#DC2626', color: '#fff',
              border: 'none', borderRadius: '7px', fontSize: '12.5px', fontWeight: '600', cursor: 'pointer',
            }}>Delete</button>
            <button onClick={handleCancel} style={{
              padding: '7px 14px', background: '#F5F5F4', color: '#525252',
              border: '1px solid #E5E5E5', borderRadius: '7px', fontSize: '12.5px', fontWeight: '600', cursor: 'pointer',
            }}>Cancel</button>
          </div>
        </div>
      )}

      {/* Icon */}
      <div style={{
        width: '42px', height: '42px',
        background: hovered ? '#FDF4EC' : '#F5F5F4',
        border: `1px solid ${hovered ? '#E8C9A8' : '#EBEBEB'}`,
        borderRadius: '10px',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginBottom: '16px',
        transition: 'background 0.18s ease, border-color 0.18s ease',
        flexShrink: 0,
      }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
          stroke={hovered ? '#C58656' : '#A3A3A3'}
          strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
          style={{ transition: 'stroke 0.18s ease' }}>
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
          <polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
      </div>

      <p style={{
        fontSize: '15px', fontWeight: '600', color: '#1A1A1A',
        marginBottom: '5px', letterSpacing: '-0.2px', lineHeight: '1.3', wordBreak: 'break-word',
      }}>{name}</p>

      <p style={{ fontSize: '12px', color: '#A3A3A3', fontWeight: '400' }}>
        {floors} {floors === 1 ? 'floor' : 'floors'} &nbsp;·&nbsp; 3D model
      </p>

      {/* Arrow reveal */}
      {!confirming && (
        <div style={{
          position: 'absolute', right: '18px', bottom: '18px',
          opacity: hovered ? 1 : 0,
          transform: hovered ? 'translateX(0)' : 'translateX(-6px)',
          transition: 'opacity 0.18s ease, transform 0.18s ease',
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="#C58656" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14"/><path d="M12 5l7 7-7 7"/>
          </svg>
        </div>
      )}
    </div>
  );
}

function RenameModal({ currentName, onSave, onClose }) {
  const [value, setValue] = useState(currentName);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!value.trim()) return;
    setSaving(true);
    await onSave(value.trim());
    setSaving(false);
  };

  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
        background: 'rgba(15, 15, 15, 0.45)',
        backdropFilter: 'blur(6px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1100,
      }}
      onClick={(e) => { if (e.target === e.currentTarget && !saving) onClose(); }}
    >
      <div style={{
        background: '#FFFFFF', borderRadius: '16px',
        width: '400px', maxWidth: '92vw',
        boxShadow: '0 20px 60px rgba(0,0,0,0.18)',
        border: '1px solid #EBEBEB', overflow: 'hidden',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '20px 24px 16px', borderBottom: '1px solid #F5F5F4',
        }}>
          <h2 style={{
            fontFamily: "'Outfit', sans-serif",
            fontSize: '17px', fontWeight: '700', color: '#1A1A1A', letterSpacing: '-0.3px',
          }}>Rename Project</h2>
          {!saving && (
            <button onClick={onClose} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: '28px', height: '28px', background: '#F5F5F4',
              border: 'none', borderRadius: '7px', cursor: 'pointer', color: '#737373',
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          )}
        </div>

        <form onSubmit={handleSubmit} style={{ padding: '20px 24px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '7px' }}>
            <label style={{
              fontSize: '12px', fontWeight: '600', color: '#525252',
              letterSpacing: '0.02em', textTransform: 'uppercase',
            }}>Project Name</label>
            <input
              type="text"
              value={value}
              onChange={e => setValue(e.target.value)}
              autoFocus
              disabled={saving}
              style={{
                width: '100%', padding: '10px 13px',
                border: '1px solid #E5E5E5', borderRadius: '9px',
                fontSize: '14px', color: '#1A1A1A',
                background: '#FAFAFA', outline: 'none',
                fontFamily: "'Inter', sans-serif",
                boxSizing: 'border-box',
              }}
            />
          </div>

          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
            <button type="button" onClick={onClose} disabled={saving} style={{
              padding: '9px 16px', background: '#F5F5F4', color: '#525252',
              border: '1px solid #E5E5E5', borderRadius: '8px',
              fontSize: '13.5px', fontWeight: '600', cursor: 'pointer',
            }}>Cancel</button>
            <button type="submit" disabled={saving || !value.trim()} style={{
              padding: '9px 18px',
              background: value.trim() && !saving ? '#1A1A1A' : '#E5E5E5',
              color: value.trim() && !saving ? '#FFFFFF' : '#A3A3A3',
              border: 'none', borderRadius: '8px',
              fontSize: '13.5px', fontWeight: '600',
              cursor: value.trim() && !saving ? 'pointer' : 'not-allowed',
              transition: 'background 0.15s ease',
            }}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EmptyState({ onCreateClick }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: '80px 20px', textAlign: 'center', maxWidth: '340px', margin: '0 auto',
    }}>
      <div style={{ marginBottom: '22px' }}>
        <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
          <rect x="10" y="6" width="36" height="44" rx="4" stroke="#E2E2E2" strokeWidth="2"/>
          <path d="M18 18h20M18 25h20M18 32h13" stroke="#D1D5DB" strokeWidth="2" strokeLinecap="round"/>
          <circle cx="38" cy="38" r="6" stroke="#C58656" strokeWidth="2"/>
          <path d="M42.5 42.5l3.5 3.5" stroke="#C58656" strokeWidth="2.5" strokeLinecap="round"/>
        </svg>
      </div>
      <h3 style={{
        fontFamily: "'Outfit', sans-serif", fontSize: '19px', fontWeight: '600',
        color: '#1A1A1A', marginBottom: '8px', letterSpacing: '-0.3px',
      }}>No projects yet</h3>
      <p style={{ fontSize: '14px', color: '#9CA3AF', lineHeight: '1.65', marginBottom: '28px' }}>
        Upload a floor-plan blueprint to generate an interactive 3D model.
      </p>
      <button onClick={onCreateClick} style={{
        display: 'inline-flex', alignItems: 'center', gap: '8px',
        background: '#C58656', color: '#FFFFFF',
        padding: '11px 22px', borderRadius: '10px', border: 'none',
        fontSize: '14px', fontWeight: '600', cursor: 'pointer',
        letterSpacing: '-0.1px', boxShadow: '0 1px 3px rgba(197, 134, 86, 0.3)',
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        Upload Blueprint
      </button>
    </div>
  );
}

function UploadModal({ projectName, onNameChange, onUpload, onDrop, isDragging, setIsDragging, status, progress, onClose }) {
  const isLoading = status !== '' && !status.startsWith('error:');
  const isError = status && status.startsWith('error:');

  const statusMsg = isError ? status.replace('error:', '') : status;

  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
        background: 'rgba(15, 15, 15, 0.45)', backdropFilter: 'blur(6px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
      onClick={(e) => { if (e.target === e.currentTarget && !isLoading) onClose(); }}
    >
      <div style={{
        background: '#FFFFFF', borderRadius: '16px', width: '460px', maxWidth: '92vw',
        boxShadow: '0 20px 60px rgba(0,0,0,0.18)', border: '1px solid #EBEBEB', overflow: 'hidden',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '22px 26px 18px', borderBottom: '1px solid #F5F5F4',
        }}>
          <h2 style={{
            fontFamily: "'Outfit', sans-serif", fontSize: '19px', fontWeight: '700',
            color: '#1A1A1A', letterSpacing: '-0.4px',
          }}>New Project</h2>
          {!isLoading && (
            <button onClick={onClose} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: '30px', height: '30px', background: '#F5F5F4',
              border: 'none', borderRadius: '7px', cursor: 'pointer', color: '#737373',
            }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          )}
        </div>

        <div style={{ padding: '22px 26px 26px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '7px' }}>
            <label style={{
              fontSize: '12px', fontWeight: '600', color: '#525252',
              letterSpacing: '0.02em', textTransform: 'uppercase',
            }}>Project Name</label>
            <input
              type="text"
              value={projectName}
              onChange={e => onNameChange(e.target.value)}
              placeholder="e.g. Skyline Residence"
              disabled={isLoading}
              style={{
                width: '100%', padding: '10px 13px',
                border: '1px solid #E5E5E5', borderRadius: '9px',
                fontSize: '14px', color: '#1A1A1A',
                background: '#FAFAFA', outline: 'none',
                fontFamily: "'Inter', sans-serif", marginBottom: '0', boxSizing: 'border-box',
              }}
            />
          </div>

          <div
            style={{
              border: `1.5px dashed ${isDragging ? '#C58656' : '#D1D5DB'}`,
              borderRadius: '12px', padding: '28px 20px', textAlign: 'center',
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              background: isDragging ? '#FDF4EC' : '#FAFAFA', transition: 'all 0.18s ease',
            }}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={onDrop}
          >
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none"
              stroke={isDragging ? '#C58656' : '#9CA3AF'}
              strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
              style={{ marginBottom: '10px', transition: 'stroke 0.18s ease' }}>
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <p style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '4px' }}>
              Drop blueprint here
            </p>
            <p style={{ fontSize: '12px', color: '#9CA3AF', marginBottom: '14px' }}>PNG, JPG, or PDF</p>
            <label htmlFor="file-upload" style={{
              display: 'inline-flex', alignItems: 'center', padding: '8px 16px',
              background: '#FFFFFF', border: '1px solid #D1D5DB', borderRadius: '8px',
              fontSize: '13px', fontWeight: '600', color: '#374151',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              opacity: isLoading ? 0.5 : 1, transition: 'all 0.15s ease',
            }}>Browse files</label>
            <input type="file" id="file-upload" style={{ display: 'none' }}
              accept="image/png, image/jpeg, application/pdf"
              onChange={onUpload} disabled={isLoading} multiple />
          </div>

          {statusMsg && (
            <div style={{
              display: 'flex', flexDirection: 'column', gap: '10px',
              padding: '14px 16px', borderRadius: '10px',
              background: isError ? '#FEF2F2' : '#FDF4EC',
              border: `1px solid ${isError ? '#FECACA' : '#FCD6A4'}`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '13.5px', fontWeight: '500', color: isError ? '#991B1B' : '#92400E' }}>
                {isLoading && <div className="dash-spinner" />}
                {isError ? statusMsg : "Processing..."}
              </div>
              {isLoading && !isError && progress !== undefined && (
                <div style={{ width: '100%', height: '6px', background: 'rgba(197, 134, 86, 0.2)', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ width: `${progress}%`, height: '100%', background: '#C58656', borderRadius: '4px', transition: 'width 0.3s ease' }} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   Main Dashboard
───────────────────────────────────────────────────────────── */

function Dashboard() {
  const [projects, setProjects] = useState([]);
  const [showUpload, setShowUpload] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [uploadStatus, setUploadStatus] = useState('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [logoutHover, setLogoutHover] = useState(false);
  const [createHover, setCreateHover] = useState(false);
  const [renamingProject, setRenamingProject] = useState(null); // { project_id, name }

  const navigate = useNavigate();
  const userId = localStorage.getItem('user_id');

  useEffect(() => {
    if (!userId) { navigate('/login'); return; }
    loadProjects();
  }, [userId]);

  const loadProjects = async () => {
    try {
      const data = await fetchApi(`/projects/${userId}?t=${Date.now()}`);
      setProjects(data.projects || []);
    } catch (e) {
      console.error(e);
      if (e.message.includes('401')) { removeToken(); navigate('/login'); }
    }
  };

  const handleLogout = async (e) => {
    e.preventDefault();
    try { await fetchApi('/auth/logout', { method: 'POST' }); } catch (_) {}
    removeToken();
    localStorage.removeItem('user_id');
    navigate('/login');
  };

  const openUpload = () => {
    setShowUpload(true);
    setUploadStatus('');
    setNewProjectName('');
  };

  const processFiles = async (selectedFiles) => {
    if (!selectedFiles || !selectedFiles.length) return;
    setUploadStatus('Initializing upload...');
    setUploadProgress(0);

    const formData = new FormData();
    for (let i = 0; i < selectedFiles.length; i++) {
      formData.append('files', selectedFiles[i]);
    }

    try {
      const data = await fetchSSEForm('/upload', formData, (pct, msg) => {
        setUploadProgress(pct);
        setUploadStatus(msg);
      });

      setUploadStatus('Saving project...');
      setUploadProgress(100);

      const saveRes = await fetchApi('/projects/save', {
        method: 'POST',
        body: JSON.stringify({
          user_id: userId,
          name: newProjectName || 'Untitled Project',
          rawBackendData: data.floors,
        }),
      });

      navigate(`/annotate?project_id=${saveRes.project_id}`);
    } catch (err) {
      setUploadStatus(`error:${err.message}`);
    }
  };

  const handleDelete = async (projectId) => {
    try {
      await fetchApi(`/projects/${projectId}`, { method: 'DELETE' });
      setProjects((prev) => prev.filter((p) => p.project_id !== projectId));
    } catch (e) {
      console.error('Delete failed:', e);
    }
  };

  const handleRename = async (projectId, newName) => {
    try {
      await fetchApi(`/projects/${projectId}/rename`, {
        method: 'PATCH',
        body: JSON.stringify({ name: newName }),
      });
      setProjects((prev) =>
        prev.map((p) => p.project_id === projectId ? { ...p, name: newName } : p)
      );
      setRenamingProject(null);
    } catch (e) {
      console.error('Rename failed:', e);
    }
  };

  const handleUpload = (e) => processFiles(e.target.files);

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    processFiles(e.dataTransfer.files);
  };

  const initials = userId ? userId.charAt(0).toUpperCase() : 'U';

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#FAFAF8', fontFamily: "'Inter', sans-serif" }}>

      {/* ── Sidebar ─────────────────────────────────── */}
      <aside style={{
        width: '280px', minWidth: '280px',
        background: '#FFFFFF',
        borderRight: '1px solid #EBEBEB',
        display: 'flex', flexDirection: 'column',
        padding: '24px 16px',
        height: '100vh',
        boxSizing: 'border-box',
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '32px', padding: '0 8px' }}>
          <div style={{
            width: '30px', height: '30px', borderRadius: '8px',
            background: '#C58656',
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
              <polyline points="9 22 9 12 15 12 15 22"/>
            </svg>
          </div>
          <span style={{
            fontFamily: "'Outfit', sans-serif",
            fontSize: '16px', fontWeight: '700',
            color: '#1A1A1A', letterSpacing: '-0.3px',
          }}>ArchTransform</span>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1 }}>
          <p style={{
            fontSize: '10.5px', fontWeight: '600', color: '#C2C2C2',
            letterSpacing: '0.09em', textTransform: 'uppercase',
            padding: '0 10px', marginBottom: '6px',
          }}>Workspace</p>

          <a href="#" style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            padding: '9px 12px',
            textDecoration: 'none',
            color: '#C58656',
            fontSize: '13.5px', fontWeight: '600',
            borderRadius: '8px',
            background: '#FDF4EC',
            border: '1px solid rgba(197,134,86,0.15)',
          }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="7" height="7" rx="1"/>
              <rect x="14" y="3" width="7" height="7" rx="1"/>
              <rect x="14" y="14" width="7" height="7" rx="1"/>
              <rect x="3" y="14" width="7" height="7" rx="1"/>
            </svg>
            Projects
          </a>
        </nav>

        {/* Footer */}
        <div style={{ paddingTop: '16px', borderTop: '1px solid #F0F0EE' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', marginBottom: '4px' }}>
            <div style={{
              width: '32px', height: '32px', borderRadius: '50%',
              background: '#FDF4EC', border: '1.5px solid #E8C9A8',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '12px', fontWeight: '700', color: '#C58656', flexShrink: 0,
            }}>{initials}</div>
            <div style={{ overflow: 'hidden' }}>
              <p style={{
                fontSize: '13px', fontWeight: '600', color: '#1A1A1A',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>My Account</p>
              <p style={{ fontSize: '11px', color: '#B0B0B0' }}>Professional</p>
            </div>
          </div>

          <button
            onClick={handleLogout}
            onMouseEnter={() => setLogoutHover(true)}
            onMouseLeave={() => setLogoutHover(false)}
            style={{
              display: 'flex', alignItems: 'center', gap: '9px',
              width: '100%', padding: '9px 12px',
              background: logoutHover ? '#F5F5F4' : 'transparent',
              border: 'none', borderRadius: '8px',
              color: logoutHover ? '#1A1A1A' : '#A3A3A3',
              fontSize: '13px', fontWeight: '500',
              cursor: 'pointer', textAlign: 'left',
              transition: 'background 0.15s ease, color 0.15s ease',
            }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            Sign out
          </button>
        </div>
      </aside>

      {/* ── Main content ────────────────────────────── */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Header */}
        <header style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '30px 40px 26px', flexShrink: 0,
        }}>
          <div>
            <h1 style={{
              fontFamily: "'Outfit', sans-serif",
              fontSize: '26px', fontWeight: '700',
              color: '#1A1A1A', letterSpacing: '-0.5px', marginBottom: '3px',
            }}>Projects</h1>
            <p style={{ fontSize: '13.5px', color: '#B0B0B0', fontWeight: '400' }}>
              {projects.length} {projects.length === 1 ? 'project' : 'projects'} in your workspace
            </p>
          </div>

          <button
            onClick={openUpload}
            onMouseEnter={() => setCreateHover(true)}
            onMouseLeave={() => setCreateHover(false)}
            style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              background: createHover ? '#333333' : '#1A1A1A',
              color: '#FFFFFF', padding: '10px 18px',
              borderRadius: '10px', border: 'none',
              fontSize: '13.5px', fontWeight: '600', cursor: 'pointer',
              letterSpacing: '-0.1px', transition: 'background 0.15s ease',
              boxShadow: '0 1px 3px rgba(0,0,0,0.12)',
            }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New Project
          </button>
        </header>

        <div style={{ height: '1px', background: '#EBEBEB', flexShrink: 0 }} />

        {/* Grid area */}
        <div style={{ flex: 1, overflow: 'auto', padding: '28px 40px' }}>
          {projects.length === 0 ? (
            <EmptyState onCreateClick={openUpload} />
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
              gap: '14px',
            }}>
              {projects.map((proj) => {
                const numFloors = proj.rawBackendData ? proj.rawBackendData.length : 0;
                return (
                  <ProjectCard
                    key={proj.project_id}
                    name={proj.name}
                    floors={numFloors}
                    onClick={() => navigate(`/annotate?project_id=${proj.project_id}`)}
                    onDelete={() => handleDelete(proj.project_id)}
                    onRename={() => setRenamingProject({ project_id: proj.project_id, name: proj.name })}
                  />
                );
              })}
            </div>
          )}
        </div>
      </main>

      {/* Upload Modal */}
      {showUpload && (
        <UploadModal
          projectName={newProjectName}
          onNameChange={setNewProjectName}
          onUpload={handleUpload}
          onDrop={handleDrop}
          isDragging={isDragging}
          setIsDragging={setIsDragging}
          status={uploadStatus}
          progress={uploadProgress}
          onClose={() => { setShowUpload(false); setUploadStatus(''); setUploadProgress(0); }}
        />
      )}

      {/* Rename Modal */}
      {renamingProject && (
        <RenameModal
          currentName={renamingProject.name}
          onSave={(newName) => handleRename(renamingProject.project_id, newName)}
          onClose={() => setRenamingProject(null)}
        />
      )}
    </div>
  );
}

export default Dashboard;
