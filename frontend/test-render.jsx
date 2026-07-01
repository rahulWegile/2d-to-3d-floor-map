import React from 'react';
import { renderToString } from 'react-dom/server';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import Editor from './src/pages/Editor.jsx';

try {
  const html = renderToString(
    <MemoryRouter initialEntries={['/editor?project_id=123']}>
      <Routes>
        <Route path="/editor" element={<Editor />} />
      </Routes>
    </MemoryRouter>
  );
  console.log("RENDER SUCCESS!");
} catch (e) {
  console.error("RENDER FAILED:", e);
}
