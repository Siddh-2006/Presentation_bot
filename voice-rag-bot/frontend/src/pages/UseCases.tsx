import { motion } from 'framer-motion';

const UseCases = () => {
    return (
        <div style={{ paddingTop: '150px', paddingBottom: '100px' }}>
            <div className="container">
                <motion.div 
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8 }}
                    style={{ textAlign: 'center', marginBottom: '5rem' }}
                >
                    <h1 style={{ fontSize: '3.5rem' }}>Transform Any <span className="text-gradient">Meeting</span></h1>
                    <p className="text-secondary" style={{ fontSize: '1.2rem' }}>From sales pitches to academic lectures.</p>
                </motion.div>

                <div className="grid-2">
                    <motion.div 
                        initial={{ opacity: 0, scale: 0.9 }}
                        whileInView={{ opacity: 1, scale: 1 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.8 }}
                    >
                        <img 
                            src="/assets/usecase_presentation.png" 
                            alt="Corporate Meeting Use Case" 
                            className="floating-img"
                            style={{ 
                                width: '100%', 
                                borderRadius: '24px',
                                border: '1px solid var(--glass-border)'
                            }} 
                        />
                    </motion.div>
                    
                    <motion.div 
                        initial={{ opacity: 0, x: 50 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.8 }}
                        style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}
                    >
                        <div className="glass-panel" style={{ padding: '2rem' }}>
                            <h3 style={{ fontSize: '1.5rem', marginBottom: '0.5rem', color: 'var(--accent-purple)' }}>B2B Sales Pitches</h3>
                            <p className="text-secondary">Voxis handles the slides while you handle the relationship. When a client interrupts with a technical question, Voxis answers instantly.</p>
                        </div>

                        <div className="glass-panel" style={{ padding: '2rem' }}>
                            <h3 style={{ fontSize: '1.5rem', marginBottom: '0.5rem', color: 'var(--accent-cyan)' }}>Academic Lectures</h3>
                            <p className="text-secondary">Load your syllabus. Voxis teaches alongside you, fielding student questions from the back of the room effortlessly.</p>
                        </div>

                        <div className="glass-panel" style={{ padding: '2rem' }}>
                            <h3 style={{ fontSize: '1.5rem', marginBottom: '0.5rem', color: 'var(--accent-blue)' }}>Internal Standups</h3>
                            <p className="text-secondary">Let Voxis run the weekly metrics review by plugging it into your data pipeline.</p>
                        </div>
                    </motion.div>
                </div>
            </div>
        </div>
    );
};

export default UseCases;
