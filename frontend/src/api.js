const API_BASE = `http://${window.location.hostname}:8081`;

export const getToken = () => localStorage.getItem('token');
export const setToken = (token) => localStorage.setItem('token', token);
export const removeToken = () => localStorage.removeItem('token');

export const fetchApi = async (endpoint, options = {}) => {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });
  
  if (!response.ok) {
    const errorText = await response.text();
    try {
      const errorJson = JSON.parse(errorText);
      throw new Error(errorJson.detail || errorJson.message || errorText);
    } catch (e) {
      if (e.message !== "API Error") throw e;
      throw new Error(errorText || "API Error");
    }
  }
  
  return response.json();
};

export const fetchApiForm = async (endpoint, formData) => {
  const headers = {};
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers,
    body: formData,
  });
  
  if (!response.ok) {
    const errorText = await response.text();
    try {
      const errorJson = JSON.parse(errorText);
      throw new Error(errorJson.detail || errorJson.message || errorText);
    } catch (e) {
      if (e.message !== "API Error") throw e;
      throw new Error(errorText || "API Error");
    }
  }
  
  return response.json();
};

export const fetchSSEForm = async (endpoint, formData, onProgress) => {
  const headers = {};
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || 'Upload failed');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let done = false;
  let finalResult = null;
  let buffer = '';

  while (!done) {
    const { value, done: readerDone } = await reader.read();
    done = readerDone;
    if (value) {
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep the incomplete line in the buffer
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6));
            if (data.status === 'progress') {
              if (onProgress) onProgress(data.progress, data.message);
            } else if (data.status === 'success') {
              finalResult = data.data;
            } else if (data.status === 'error') {
              throw new Error(data.message);
            }
          } catch (e) {
            if (e.message && e.message !== "Unexpected end of JSON input" && !e.message.includes('JSON')) {
                throw e; // Throw actual API errors
            }
          }
        }
      }
    }
  }
  return finalResult;
};
