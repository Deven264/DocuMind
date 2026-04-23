import { useState, useEffect } from 'react';
import './index.css';

const Icons = {
  Document: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline></svg>
  ),
  Upload: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
  ),
  Search: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
  ),
  Settings: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
  )
};

function App() {
  const [activeTab, setActiveTab] = useState('upload');
  const [isProcessing, setIsProcessing] = useState(false);
  const [activeDoc, setActiveDoc] = useState<any>(null);
  const [docType, setDocType] = useState('No Document Selected');
  const [extractedData, setExtractedData] = useState<Record<string, string>>({
    "Status": "Waiting for document upload..."
  });
  const [history, setHistory] = useState<any[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const fetchHistory = async () => {
    setLoadingHistory(true);
    try {
      const res = await fetch('http://localhost:8000/api/documents');
      if (!res.ok) throw new Error('Failed to fetch history');
      const data = await res.json();
      setHistory(data);
      if (data.length > 0 && !activeDoc) {
        // Automatically select the first document if none is selected
        setActiveDoc(data[0]);
        setDocType(data[0].document_type);
        setExtractedData(data[0].extracted);
      }
    } catch (err) {
      console.error('History fetch failed:', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const deleteDocument = async (e: React.MouseEvent, docId: number) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to completely delete this document from the vault and hard drive?")) return;
    
    try {
      const res = await fetch(`http://localhost:8000/api/documents/${docId}`, { method: 'DELETE' });
      if (res.ok) {
        if (activeDoc && activeDoc.id === docId) {
          setActiveDoc(null);
          setDocType('No Document Selected');
          setExtractedData({"Status": "Waiting for document upload..."});
        }
        await fetchHistory();
      } else {
        alert("Failed to delete document.");
      }
    } catch (err) {
      alert("Error reaching backend for deletion.");
    }
  };

  const handleFileUpload = async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    setIsProcessing(true);

    try {
      const res = await fetch('http://localhost:8000/api/upload', {
        method: 'POST',
        body: formData
      });
      
      const data = await res.json();
      
      if (!res.ok) {
        alert(`Process Failed: ${data.detail || 'Internal AI Error'}`);
        return;
      }

      const newDocObj = {
          id: data.id,
          filename: data.filename,
          document_type: data.document_type,
          extracted: data.extracted,
          file_path: data.file_path, // New
          created_at: new Date().toISOString()
      };
      
      setActiveDoc(newDocObj);
      setDocType(data.document_type);
      setExtractedData(data.extracted);
      setActiveTab('search');
    } catch (err) {
      alert('Connection Error: The backend or Ollama might be busy. Please check the logs.');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="app-container">
      <aside className="sidebar">
        <div className="brand" onClick={() => setActiveTab('upload')} style={{ cursor: 'pointer' }}>
          <Icons.Document /> Docu<span>Mind</span>
        </div>
        
        <nav className="nav-menu">
          <div 
            className={`nav-item ${activeTab === 'upload' ? 'active' : ''}`}
            onClick={() => setActiveTab('upload')}
          >
            <Icons.Upload /> Process New
          </div>
          <div 
            className={`nav-item ${activeTab === 'search' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('search');
              fetchHistory();
            }}
          >
            <Icons.Search /> Repository
          </div>
        </nav>
      </aside>

      <main className="main-content">
        <header className="header">
          <h1>
            {activeTab === 'upload' ? 'Upload & Analyze' : 'Document Repository'}
          </h1>
          <p>
            {activeTab === 'upload' 
              ? 'Drop your business documents here. Local AI will extract key fields autonomously.' 
              : 'Browse your historical document bank and review extracted intelligence.'}
          </p>
        </header>

        {activeTab === 'upload' && (
          <div className="glass-panel" style={{ padding: '0' }}>
            <div 
              className="dropzone"
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
              onDrop={(e) => {
                e.preventDefault();
                e.stopPropagation();
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                  handleFileUpload(e.dataTransfer.files[0]);
                }
              }}
              onClick={() => !isProcessing && document.getElementById('fileInput')?.click()}
              style={{
                padding: '100px 40px',
                textAlign: 'center',
                border: '2px dashed var(--panel-border)',
                borderRadius: 'var(--radius-lg)',
                cursor: isProcessing ? 'wait' : 'pointer',
                transition: 'all 0.3s ease'
              }}
            >
              <Icons.Upload />
              <h2 style={{ marginTop: '20px' }}>
                {isProcessing ? 'AI is Processing...' : 'Ready for Document'}
              </h2>
              <p style={{ color: 'var(--text-muted)', marginTop: '10px' }}>
                {isProcessing 
                  ? 'Analyzing text patterns on local CPU. This can take 30-90 seconds.' 
                  : 'Drag PDF or Image here to begin. No data leaves this device.'}
              </p>
              {!isProcessing && <button className="btn" style={{ marginTop: '30px' }}>Select File</button>}
              <input 
                id="fileInput" 
                type="file" 
                style={{ display: 'none' }} 
                onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])} 
              />
            </div>
          </div>
        )}

        {activeTab === 'search' && (
          <div className="repository-container" style={{ gridTemplateColumns: activeDoc ? '280px 1fr 350px' : '350px 1fr', height: 'calc(100vh - 180px)' }}>
            <div className="glass-panel" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
              <h3 style={{ marginBottom: '20px' }}>History</h3>
              {loadingHistory ? (
                <p style={{ color: 'var(--text-muted)' }}>Updating ledger...</p>
              ) : history.length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>Repository is empty.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {history.map((doc) => (
                    <div 
                      key={doc.id} 
                      className={`glass-panel ${activeDoc && activeDoc.id === doc.id ? 'active-card' : ''}`} 
                      style={{ 
                          padding: '12px', 
                          cursor: 'pointer', 
                          border: activeDoc && activeDoc.id === doc.id ? '1px solid var(--accent-color)' : '1px solid var(--panel-border)',
                          transform: activeDoc && activeDoc.id === doc.id ? 'scale(1.02)' : 'none'
                      }}
                      onClick={() => {
                        setActiveDoc(doc);
                        setDocType(doc.document_type);
                        setExtractedData(doc.extracted);
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--accent-color)', fontWeight: 'bold' }}>{doc.document_type}</span>
                        <button 
                            onClick={(e) => deleteDocument(e, doc.id)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--danger)', fontSize: '16px' }}
                            title="Delete"
                        >
                            🗑️
                        </button>
                      </div>
                      <div style={{ fontSize: '13px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{doc.filename}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {activeDoc && activeDoc.file_path && (
                <div className="glass-panel" style={{ padding: '0', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                  <div style={{ padding: '12px 16px', background: 'rgba(0,0,0,0.4)', borderBottom: '1px solid var(--panel-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                     <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Original Document Viewer</span>
                     <a href={`http://localhost:8000${activeDoc.file_path}`} target="_blank" rel="noreferrer" className="btn" style={{ fontSize: '12px', padding: '6px 12px', textDecoration: 'none' }}>
                       Download File
                     </a>
                  </div>
                  <iframe 
                      src={`http://localhost:8000${activeDoc.file_path}`} 
                      style={{ flex: 1, width: '100%', border: 'none', background: '#ccc' }}
                      title="Raw Document Viewer"
                  />
                </div>
            )}

            <div className="glass-panel" style={{ overflowY: 'auto' }}>
              <h3 style={{ marginBottom: '20px' }}>Extracted Attributes</h3>
              <div style={{ padding: '12px', background: 'rgba(99, 102, 241, 0.1)', borderRadius: '8px', marginBottom: '24px', border: '1px solid var(--accent-color)' }}>
                <span style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Classification</span>
                <div style={{ fontSize: '18px', fontWeight: 'bold' }}>{docType}</div>
              </div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {Object.entries(extractedData).map(([key, val]) => (
                  <div key={key}>
                    <label style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '4px', display: 'block' }}>{key}</label>
                    <div style={{ padding: '12px', background: 'rgba(0,0,0,0.2)', border: '1px solid var(--panel-border)', borderRadius: '6px', fontSize: '14px' }}>
                      {val}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
