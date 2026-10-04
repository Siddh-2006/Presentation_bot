import { ArrowRight, Mic, Presentation, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';

const Landing = () => {
    return (
        <div style={{ paddingBottom: '100px' }}>
            {/* Hero Section */}
            <section className="hero container" style={{ paddingTop: '150px' }}>
                <div className="grid-2">
                    <motion.div 
                        initial={{ opacity: 0, x: -50 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.8 }}
                        className="hero-content"
                        style={{ textAlign: 'left' }}
                    >
                        <h1 style={{ fontSize: '4.5rem', lineHeight: '1.1' }}>
                            Present with <br />
                            <span className="text-gradient">Voxis.ai</span>
                        </h1>
                        <p style={{ fontSize: '1.25rem', color: 'var(--text-secondary)', marginBottom: '2.5rem', maxWidth: '500px' }}>
                            Your autonomous AI co-presenter. Complete hands-free slide navigation, 
                            real-time Voice RAG intelligence, and dynamic Q&A handling.
                        </p>
                        <div style={{ display: 'flex', gap: '1rem' }}>
                            <Link to="/dashboard" className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '1rem 2rem', fontSize: '1.1rem' }}>
                                Start Presenting <ArrowRight size={20} />
                            </Link>
                            <Link to="/features" className="btn btn-outline" style={{ padding: '1rem 2rem', fontSize: '1.1rem' }}>
                                View Demo
                            </Link>
                        </div>
                    </motion.div>
                    
                    <motion.div 
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ duration: 1 }}
                        style={{ position: 'relative' }}
                    >
                        {/* Glow effect behind image */}
                        <div style={{
                            position: 'absolute',
                            top: '50%',
                            left: '50%',
                            transform: 'translate(-50%, -50%)',
                            width: '400px',
                            height: '400px',
                            background: 'var(--accent-purple)',
                            filter: 'blur(150px)',
                            opacity: 0.3,
                            zIndex: -1
                        }}></div>
                        <img 
                            src="/assets/hero_bot.png" 
                            alt="Voxis AI Bot" 
                            className="floating-img" 
                            style={{ 
                                width: '100%', 
                                maxWidth: '500px', 
                                display: 'block', 
                                margin: '0 auto',
                                borderRadius: '24px',
                                border: '1px solid var(--glass-border)'
                            }} 
                        />
                    </motion.div>
                </div>
            </section>

            {/* Elite Features Overview */}
            <section className="container" style={{ marginTop: '5rem' }}>
                <motion.div 
                    initial={{ opacity: 0, y: 50 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6 }}
                    className="grid-3"
                >
                    <div className="glass-panel" style={{ textAlign: 'center', padding: '3rem 2rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.5rem' }}>
                            <div style={{ background: 'var(--glass-bg)', padding: '1rem', borderRadius: '50%', border: '1px solid var(--glass-border)' }}>
                                <Mic size={32} className="text-gradient" />
                            </div>
                        </div>
                        <h3 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>Sub-second Latency</h3>
                        <p className="text-secondary">Powered by Groq LPUs, Voxis processes audio and generates responses instantly alongside you.</p>
                    </div>
                    
                    <div className="glass-panel" style={{ textAlign: 'center', padding: '3rem 2rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.5rem' }}>
                            <div style={{ background: 'var(--glass-bg)', padding: '1rem', borderRadius: '50%', border: '1px solid var(--glass-border)' }}>
                                <Presentation size={32} className="text-gradient" />
                            </div>
                        </div>
                        <h3 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>Auto-Navigation</h3>
                        <p className="text-secondary">Seamlessly transitions your PowerPoint slides automatically as it finishes speaking paragraphs.</p>
                    </div>

                    <div className="glass-panel" style={{ textAlign: 'center', padding: '3rem 2rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.5rem' }}>
                            <div style={{ background: 'var(--glass-bg)', padding: '1rem', borderRadius: '50%', border: '1px solid var(--glass-border)' }}>
                                <Zap size={32} className="text-gradient" />
                            </div>
                        </div>
                        <h3 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>RAG Intelligence</h3>
                        <p className="text-secondary">It reads your slides. When the audience asks a question, Voxis answers accurately based on your data.</p>
                    </div>
                </motion.div>
            </section>

            {/* Split Content Section */}
            <section className="container" style={{ marginTop: '8rem' }}>
                <div className="grid-2">
                    <motion.div 
                        initial={{ opacity: 0, x: -50 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.8 }}
                    >
                        <img 
                            src="/assets/feature_rag.png" 
                            alt="Voice RAG Intelligence" 
                            className="floating-img"
                            style={{ 
                                width: '100%', 
                                borderRadius: '24px',
                                border: '1px solid var(--glass-border)',
                                animationDelay: '-3s'
                            }} 
                        />
                    </motion.div>
                    
                    <motion.div 
                        initial={{ opacity: 0, x: 50 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.8 }}
                        style={{ textAlign: 'left' }}
                    >
                        <h2 style={{ fontSize: '3rem', marginBottom: '1.5rem' }}>
                            Flawless <span className="text-gradient">Intelligence</span>
                        </h2>
                        <p style={{ fontSize: '1.2rem', color: 'var(--text-secondary)', marginBottom: '2rem' }}>
                            Our Voice RAG (Retrieval-Augmented Generation) pipeline doesn't just read a script. It embeds your entire presentation into a vector space. When interrupted, it searches the knowledge base and synthesizes a perfect answer.
                        </p>
                        <ul style={{ listStyle: 'none', color: 'var(--text-secondary)', fontSize: '1.1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                            <li style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><ArrowRight size={18} className="text-gradient" /> Meta Llama-3 70B Core</li>
                            <li style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><ArrowRight size={18} className="text-gradient" /> Groq Whisper Speech Recognition</li>
                            <li style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><ArrowRight size={18} className="text-gradient" /> ChromaDB Vector Storage</li>
                        </ul>
                    </motion.div>
                </div>
            </section>
        </div>
    );
};

export default Landing;
