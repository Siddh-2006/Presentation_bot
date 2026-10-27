import { useEffect, useState, useRef } from 'react';
import { motion } from 'framer-motion';
import { Settings, Play, LogOut, StopCircle, CheckCircle2, AlertCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE = API_BASE.replace(/^http/, 'ws') + '/ppt/ws';

const Dashboard = () => {
    const [user, setUser] = useState<{name: string, email: string, picture: string} | null>(null);
    const [loading, setLoading] = useState(true);
    const navigate = useNavigate();

    // App State
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [liveState, setLiveState] = useState<'idle' | 'presenting' | 'listening' | 'thinking' | 'responding'>('idle');
    const [isLive, setIsLive] = useState(false);
    
    // File Upload State
    const [docFile, setDocFile] = useState<File | null>(null);
    const [scriptFile, setScriptFile] = useState<File | null>(null);
    const [uploadStatus, setUploadStatus] = useState<{type: 'idle' | 'loading' | 'success' | 'error', message: string}>({type: 'idle', message: ''});

    // Launch State
    const [meetingUrl, setMeetingUrl] = useState('');
    const [tone, setTone] = useState('');
    const [launchStatus, setLaunchStatus] = useState<{type: 'idle' | 'loading' | 'success' | 'error', message: string}>({type: 'idle', message: ''});

    // Live Telemetry
    const [slideInfo, setSlideInfo] = useState('Initializing...');
    const [interrupts, setInterrupts] = useState(0);
    const [currentSentence, setCurrentSentence] = useState('Initializing...');
    const [eventLog, setEventLog] = useState<{time: string, type: string, text: string}[]>([]);
    
    const wsRef = useRef<WebSocket | null>(null);
    const eventLogRef = useRef<HTMLDivElement>(null);

    const [backendStatus, setBackendStatus] = useState<{ online: boolean; modelsLoaded?: boolean; checked: boolean }>({ online: false, checked: false });

    useEffect(() => {
        // 1. Check live AWS EC2 backend connectivity
        fetch(`${API_BASE}/health`)
            .then(res => res.json())
            .then(data => setBackendStatus({ online: data.status === 'ok', modelsLoaded: data.models_loaded, checked: true }))
            .catch(() => setBackendStatus({ online: false, checked: true }));

        // 2. Auth handling (with fallback so users are never locked out of testing)
        const searchParams = new URLSearchParams(window.location.search);
        const urlToken = searchParams.get('token');
        if (urlToken) {
            localStorage.setItem('access_token', urlToken);
            window.history.replaceState({}, document.title, "/dashboard");
        }

        const token = localStorage.getItem('access_token');
        if (!token) {
            // Guest / Demo access enabled
            setUser({
                name: "Demo Presenter",
                email: "demo@voxis.ai",
                picture: "https://ui-avatars.com/api/?name=Voxis+Presenter&background=8b5cf6&color=fff"
            });
            setLoading(false);
            return;
        }

        fetch(`${API_BASE}/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        })
        .then(res => {
            if (!res.ok) throw new Error("Invalid token");
            return res.json();
        })
        .then(data => {
            setUser({
                name: data.name || "Voxis User",
                email: data.sub || "user@voxis.ai",
                picture: data.picture || "https://ui-avatars.com/api/?name=Voxis&background=8b5cf6&color=fff"
            });
            setLoading(false);
        })
        .catch(() => {
            // Graceful fallback to demo user if token expired or failed
            setUser({
                name: "Voxis Presenter",
                email: "demo@voxis.ai",
                picture: "https://ui-avatars.com/api/?name=Voxis+Presenter&background=8b5cf6&color=fff"
            });
            setLoading(false);
        });
    }, [navigate]);

    const handleLogout = () => {
        localStorage.removeItem('access_token');
        navigate('/');
    };

    const handleUpload = async () => {
        if (!docFile || !scriptFile) {
            setUploadStatus({type: 'error', message: 'Please select both files.'});
            return;
        }

        setUploadStatus({type: 'loading', message: 'Processing files and embedding knowledge...'});
        const formData = new FormData();
        formData.append('document_file', docFile);
        formData.append('script_file', scriptFile);

        try {
            const res = await fetch(`${API_BASE}/ppt/upload`, {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            
            if (res.ok && data.session_id) {
                setSessionId(data.session_id);
                setUploadStatus({type: 'success', message: 'Files processed successfully!'});
            } else {
                setUploadStatus({type: 'error', message: `Failed: ${data.error || 'Unknown error'}`});
            }
        } catch (e: any) {
            setUploadStatus({type: 'error', message: `Connection error: ${e.message}`});
        }
    };

    const handleLaunch = async () => {
        if (!sessionId) {
            setLaunchStatus({type: 'error', message: 'Please upload files first.'});
            return;
        }
        if (!meetingUrl) {
            setLaunchStatus({type: 'error', message: 'Please enter a meeting URL.'});
            return;
        }

        setLaunchStatus({type: 'loading', message: 'Joining meeting...'});
        const formData = new FormData();
        formData.append('meeting_url', meetingUrl);
        formData.append('session_id', sessionId);
        if (tone) {
            formData.append('tone', tone);
        }

        try {
            const res = await fetch(`${API_BASE}/ppt/start`, {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            
            if (res.ok && data.status === 'live') {
                setLaunchStatus({type: 'success', message: 'Bot joined the meeting!'});
                startLiveSession();
            } else {
                setLaunchStatus({type: 'error', message: `Failed to join: ${data.error || 'Unknown error'}`});
            }
        } catch (e: any) {
            setLaunchStatus({type: 'error', message: `Connection error: ${e.message}`});
        }
    };

    const getTimestring = () => {
        const d = new Date();
        return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
    };

    const addLog = (type: string, text: string) => {
        setEventLog(prev => {
            const newLog = [...prev, { time: getTimestring(), type, text }];
            if (newLog.length > 50) return newLog.slice(newLog.length - 50);
            return newLog;
        });
        setTimeout(() => {
            if (eventLogRef.current) {
                eventLogRef.current.scrollTop = eventLogRef.current.scrollHeight;
            }
        }, 100);
    };

    const startLiveSession = () => {
        setIsLive(true);
        setEventLog([]);
        connectWS();
    };

    const stopSession = async () => {
        try {
            await fetch(`${API_BASE}/ppt/stop`, { method: 'POST' });
        } catch (e) { console.error("Error stopping", e); }
        
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        setIsLive(false);
        setLiveState('idle');
    };

    const connectWS = () => {
        if (wsRef.current) wsRef.current.close();
        
        const ws = new WebSocket(WS_BASE);
        wsRef.current = ws;

        ws.onopen = () => addLog('STATE', 'WebSocket Connected');
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.status) {
                    setLiveState(data.status.toLowerCase());
                    setSlideInfo(`Slide ${data.slide} · Sentence ${data.sentence}`);
                    setInterrupts(data.interrupts);
                    if (data.status.toLowerCase() === 'idle') {
                        stopSession();
                    }
                } else if (data.event) {
                    switch(data.event) {
                        case 'SPEAKING':
                            setCurrentSentence(`"${data.text}"`);
                            addLog('SPEAKING', `Bot: "${data.text}"`);
                            break;
                        case 'TRANSCRIPT':
                            addLog('TRANSCRIPT', `Human: "${data.text}"`);
                            break;
                        case 'RESPONDING':
                            setCurrentSentence(`"${data.text || 'Generating response...'}"`);
                            addLog('RESPONDING', `Bot replies: "${data.text || 'Generating...'}"`);
                            break;
                        case 'SLIDE_ADVANCE':
                            addLog('STATE', `Advanced to slide ${data.slide}`);
                            break;
                        case 'THINKING':
                            setCurrentSentence(`Thinking...`);
                            break;
                        default:
                            addLog('STATE', data.event);
                    }
                }
            } catch (e) {
                console.error("WS Parse Error", e);
            }
        };

        ws.onclose = () => {
            addLog('STATE', 'WebSocket Disconnected');
        };
    };

    if (loading || !user) return <div style={{ paddingTop: '150px', textAlign: 'center' }}>Loading...</div>;

    const getStateColor = () => {
        switch(liveState) {
            case 'presenting': return 'var(--success)';
            case 'listening': return 'var(--warning)';
            case 'thinking': return 'var(--accent-purple)';
            case 'responding': return 'var(--accent-blue)';
            default: return 'var(--text-muted)';
        }
    };

    return (
        <div style={{ paddingTop: '150px', paddingBottom: '100px' }}>
            <div className="container">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '3rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                        <img 
                            src={user.picture} 
                            alt="Profile" 
                            referrerPolicy="no-referrer"
                            style={{ width: '60px', borderRadius: '50%' }} 
                        />
                        <div>
                            <h2 style={{ fontSize: '2rem', margin: 0 }}>Welcome back, {user.name}</h2>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                                <span style={{
                                    display: 'inline-block',
                                    width: '10px',
                                    height: '10px',
                                    borderRadius: '50%',
                                    backgroundColor: backendStatus.online ? '#22c55e' : '#ef4444',
                                    boxShadow: backendStatus.online ? '0 0 8px #22c55e' : 'none'
                                }} />
                                <span style={{ fontSize: '0.85rem', color: backendStatus.online ? '#86efac' : '#fca5a5', fontWeight: 500 }}>
                                    {backendStatus.checked
                                        ? (backendStatus.online ? `Live Backend: ${API_BASE} (Models Ready)` : `Backend Offline: ${API_BASE}`)
                                        : 'Connecting to AWS backend...'}
                                </span>
                            </div>
                        </div>
                    </div>
                    <button onClick={handleLogout} className="btn btn-outline" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <LogOut size={18} /> Logout
                    </button>
                </div>

                {!isLive ? (
                    <div className="grid-2">
                        {/* Configure RAG / Upload */}
                        <motion.div 
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="glass-panel"
                        >
                            <Settings size={32} className="text-gradient" style={{ marginBottom: '1rem' }} />
                            <h3>1. Configure Knowledge (RAG)</h3>
                            <p className="text-secondary" style={{ marginBottom: '1.5rem' }}>Upload your Presentation and Script for vectorization.</p>
                            
                            <div style={{ marginBottom: '1rem' }}>
                                <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Presentation (PDF/PPTX)</label>
                                <input type="file" accept=".pdf,.pptx" onChange={e => setDocFile(e.target.files?.[0] || null)} style={{ width: '100%', color: 'white' }} />
                            </div>

                            <div style={{ marginBottom: '1.5rem' }}>
                                <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Spoken Script (JSON)</label>
                                <input type="file" accept=".json" onChange={e => setScriptFile(e.target.files?.[0] || null)} style={{ width: '100%', color: 'white' }} />
                            </div>

                            <button onClick={handleUpload} className="btn btn-outline" style={{ width: '100%' }} disabled={uploadStatus.type === 'loading'}>
                                {uploadStatus.type === 'loading' ? 'Processing...' : 'Upload & Process'}
                            </button>

                            {uploadStatus.message && (
                                <div style={{ marginTop: '1rem', padding: '0.5rem', borderRadius: '8px', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '8px',
                                    background: uploadStatus.type === 'success' ? 'rgba(16, 185, 129, 0.1)' : uploadStatus.type === 'error' ? 'rgba(239, 68, 68, 0.1)' : 'transparent',
                                    color: uploadStatus.type === 'success' ? '#10b981' : uploadStatus.type === 'error' ? '#ef4444' : 'white'
                                }}>
                                    {uploadStatus.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                                    {uploadStatus.message}
                                </div>
                            )}
                        </motion.div>

                        {/* Launch Bot */}
                        <motion.div 
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.1 }}
                            className="glass-panel"
                            style={{ opacity: sessionId ? 1 : 0.5, pointerEvents: sessionId ? 'auto' : 'none', transition: 'all 0.3s ease' }}
                        >
                            <Play size={32} className="text-gradient" style={{ marginBottom: '1rem' }} />
                            <h3>2. Launch Session</h3>
                            <p className="text-secondary" style={{ marginBottom: '1.5rem' }}>Deploy the Voxis AI bot into your meeting.</p>
                            
                            <div style={{ marginBottom: '1rem' }}>
                                <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Meeting URL</label>
                                <input 
                                    type="text" 
                                    placeholder="https://meet.google.com/..." 
                                    value={meetingUrl}
                                    onChange={e => setMeetingUrl(e.target.value)}
                                    style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid var(--glass-border)', background: 'rgba(0,0,0,0.2)', color: 'white', outline: 'none' }}
                                />
                            </div>

                            <div style={{ marginBottom: '1.5rem' }}>
                                <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>AI Tone / Personality (Optional)</label>
                                <input 
                                    type="text" 
                                    placeholder="e.g. Professional, Funny, Energetic" 
                                    value={tone}
                                    onChange={e => setTone(e.target.value)}
                                    style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid var(--glass-border)', background: 'rgba(0,0,0,0.2)', color: 'white', outline: 'none' }}
                                />
                            </div>

                            <button onClick={handleLaunch} className="btn btn-primary" style={{ width: '100%' }} disabled={launchStatus.type === 'loading'}>
                                {launchStatus.type === 'loading' ? 'Joining Meeting...' : 'Launch Bot'}
                            </button>

                            {launchStatus.message && (
                                <div style={{ marginTop: '1rem', padding: '0.5rem', borderRadius: '8px', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '8px',
                                    background: launchStatus.type === 'success' ? 'rgba(16, 185, 129, 0.1)' : launchStatus.type === 'error' ? 'rgba(239, 68, 68, 0.1)' : 'transparent',
                                    color: launchStatus.type === 'success' ? '#10b981' : launchStatus.type === 'error' ? '#ef4444' : 'white'
                                }}>
                                    {launchStatus.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                                    {launchStatus.message}
                                </div>
                            )}
                        </motion.div>
                    </div>
                ) : (
                    /* Live Dashboard */
                    <motion.div 
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="glass-panel"
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                            <div>
                                <h3 style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '1.5rem' }}>
                                    <div style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: getStateColor(), boxShadow: `0 0 10px ${getStateColor()}` }}></div>
                                    {liveState.toUpperCase()}
                                </h3>
                                <p className="text-secondary" style={{ margin: '0.5rem 0 0 0' }}>{slideInfo} · {interrupts} Interruptions</p>
                            </div>
                            <button onClick={stopSession} className="btn btn-outline" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ef4444', borderColor: '#ef4444' }}>
                                <StopCircle size={18} /> Stop Bot
                            </button>
                        </div>

                        <div style={{ padding: '1.5rem', background: 'rgba(0,0,0,0.3)', borderRadius: '12px', borderLeft: `4px solid ${getStateColor()}`, marginBottom: '2rem' }}>
                            <p style={{ fontSize: '1.25rem', fontStyle: 'italic', margin: 0 }}>{currentSentence}</p>
                        </div>

                        <div>
                            <h4 style={{ marginBottom: '1rem', color: 'var(--text-secondary)' }}>Event Log</h4>
                            <div ref={eventLogRef} style={{ height: '200px', overflowY: 'auto', background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: '8px', fontFamily: 'monospace', fontSize: '0.85rem' }}>
                                {eventLog.map((log, i) => (
                                    <div key={i} style={{ marginBottom: '0.5rem' }}>
                                        <span style={{ color: 'var(--text-secondary)', marginRight: '0.5rem' }}>[{log.time}]</span>
                                        <span style={{ 
                                            color: log.type === 'SPEAKING' ? 'var(--primary)' : 
                                                   log.type === 'TRANSCRIPT' ? 'var(--warning)' : 
                                                   log.type === 'RESPONDING' ? 'var(--success)' : 'var(--text-secondary)' 
                                        }}>{log.text}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </motion.div>
                )}
            </div>
        </div>
    );
};

export default Dashboard;
