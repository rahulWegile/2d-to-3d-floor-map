import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchApi, setToken } from '../api';

function Login({ isSignupRoute = false }) {
  const [isLogin, setIsLogin] = useState(!isSignupRoute);
  
  useEffect(() => {
    setIsLogin(!isSignupRoute);
    setError('');
  }, [isSignupRoute]);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');

  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    try {
      const endpoint = isLogin ? '/auth/login' : '/auth/signup';
      const body = isLogin 
        ? { username, password }
        : { username, password, email };
        
      const data = await fetchApi(endpoint, {
        method: 'POST',
        body: JSON.stringify(body)
      });
      
      if (data.success) {
        setToken(data.token);
        localStorage.setItem('user_id', data.user_id);
        navigate('/dashboard');
      }
    } catch (err) {
      setError(err.message || "An error occurred");
    }
  };

  return (
    <div className="screen login-split" style={{ display: 'flex', width: '100vw', height: '100vh', margin: 0, padding: 0 }}>
      <div className="login-left" style={{ backgroundImage: "url('/images/login_bg.jpg')" }}>
        <div style={{ position: 'relative', zIndex: 10 }}>
          <div style={{
            position: 'absolute',
            top: '-50px', left: '-50px', right: '-50px', bottom: '-50px',
            background: 'radial-gradient(circle, rgba(0,0,0,0.2) 0%, rgba(0,0,0,0) 70%)',
            backdropFilter: 'blur(6px)',
            WebkitMaskImage: 'radial-gradient(circle, black 40%, transparent 70%)',
            maskImage: 'radial-gradient(circle, black 40%, transparent 70%)',
            zIndex: -1
          }}></div>

          <h1 className="logo-text" style={{ fontSize: '56px', color: '#ffffff', marginBottom: '16px', fontWeight: '700', letterSpacing: '-1px', textShadow: '0 2px 10px rgba(0,0,0,0.3)' }}>ArchTransform</h1>
          <p style={{ fontSize: '22px', color: 'rgba(255, 255, 255, 0.95)', maxWidth: '440px', lineHeight: '1.5', fontWeight: '500', textShadow: '0 2px 8px rgba(0,0,0,0.3)' }}>
            The fastest way to convert 2D architectural blueprints into fully interactive 3D environments.
          </p>
        </div>
      </div>

      <div className="login-right">
        <form className="login-form" onSubmit={handleSubmit} style={{ width: '100%', maxWidth: '380px' }}>
          <h2 style={{ fontSize: '32px', color: '#0f172a', marginBottom: '8px', fontWeight: '700', letterSpacing: '-0.5px' }}>
            {isLogin ? 'Welcome back' : 'Create an account'}
          </h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '32px', fontSize: '16px' }}>
            {isLogin ? 'Sign in to access your projects.' : 'Sign up to start building 3D spaces.'}
          </p>

          {error && <div style={{ color: '#92400e', background: 'rgba(254, 243, 199, 0.6)', border: '1px solid rgba(217, 119, 6, 0.3)', padding: '12px 16px', borderRadius: '12px', marginBottom: '24px', fontSize: '14px', fontWeight: '600', backdropFilter: 'blur(8px)', textAlign: 'center' }}>{error}</div>}

          {!isLogin && (
            <div className="input-group">
              <label>Email Address</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} required={!isLogin} placeholder="name@company.com" autoComplete="email" />
            </div>
          )}

          <div className="input-group">
            <label>{isLogin ? 'Username / Email' : 'Username'}</label>
            <input type="text" value={username} onChange={e => setUsername(e.target.value)} required placeholder={isLogin ? "Your username / email" : "Your username"} autoComplete="username" />
          </div>

          <div className="input-group">
            <label>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="••••••••" autoComplete="current-password" />
          </div>

          <button type="submit" className="upload-btn primary-btn" style={{ width: '100%', marginTop: '16px', padding: '16px', fontSize: '16px', border: 'none', fontWeight: '700', textAlign: 'center', justifyContent: 'center' }}>
            {isLogin ? 'Sign In' : 'Create Account'}
          </button>

          <p style={{ marginTop: '32px', textAlign: 'center', fontSize: '14px', color: 'var(--text-secondary)' }}>
            {isLogin ? "Don't have an account? " : "Already have an account? "}
            <a href="#" onClick={(e) => { e.preventDefault(); navigate(isLogin ? '/signup' : '/login'); }} style={{ color: '#c58656', fontWeight: '700', textDecoration: 'none' }}>
              {isLogin ? 'Sign up for free' : 'Sign in'}
            </a>
          </p>
        </form>
      </div>
    </div>
  );
}

export default Login;
