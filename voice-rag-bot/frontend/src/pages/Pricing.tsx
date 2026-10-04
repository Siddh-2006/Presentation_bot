import { motion } from 'framer-motion';
import { Check } from 'lucide-react';
import { Link } from 'react-router-dom';

const Pricing = () => {
    return (
        <div style={{ paddingTop: '150px', paddingBottom: '100px' }}>
            <div className="container">
                <motion.div 
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8 }}
                    style={{ textAlign: 'center', marginBottom: '4rem' }}
                >
                    <h1 style={{ fontSize: '3.5rem' }}>Simple, <span className="text-gradient">Transparent</span> Pricing</h1>
                    <p className="text-secondary">Start for free. Upgrade when you need more power.</p>
                </motion.div>

                <div className="grid-2" style={{ maxWidth: '900px', margin: '0 auto', gap: '2rem' }}>
                    {/* Free Tier */}
                    <motion.div 
                        initial={{ opacity: 0, x: -30 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.8 }}
                        className="glass-panel"
                    >
                        <h2>Free Tier</h2>
                        <h1 style={{ fontSize: '3rem', margin: '1rem 0' }}>$0<span style={{ fontSize: '1rem', color: 'var(--text-secondary)' }}>/mo</span></h1>
                        <p className="text-secondary" style={{ marginBottom: '2rem' }}>Perfect for students and occasional presenters.</p>
                        
                        <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '2rem' }}>
                            <li style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><Check size={18} className="text-gradient" /> 5 Presentations / month</li>
                            <li style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><Check size={18} className="text-gradient" /> Local CPU Inference Fallback</li>
                            <li style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><Check size={18} className="text-gradient" /> Standard Support</li>
                        </ul>
                        
                        <Link to="/dashboard" className="btn btn-outline" style={{ width: '100%', textAlign: 'center', display: 'block' }}>Current Plan</Link>
                    </motion.div>

                    {/* Pro Tier */}
                    <motion.div 
                        initial={{ opacity: 0, x: 30 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.8 }}
                        className="glass-panel"
                        style={{ position: 'relative', border: '1px solid var(--accent-purple)', boxShadow: '0 0 30px rgba(139, 92, 246, 0.2)' }}
                    >
                        <div style={{ position: 'absolute', top: '-15px', right: '20px', background: 'var(--accent-purple)', color: 'white', padding: '5px 15px', borderRadius: '20px', fontSize: '0.8rem', fontWeight: 'bold' }}>
                            MOST POPULAR
                        </div>
                        <h2>Voxis Pro</h2>
                        <h1 style={{ fontSize: '3rem', margin: '1rem 0' }}>$29<span style={{ fontSize: '1rem', color: 'var(--text-secondary)' }}>/mo</span></h1>
                        <p className="text-secondary" style={{ marginBottom: '2rem' }}>For professionals who present daily.</p>
                        
                        <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '2rem' }}>
                            <li style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><Check size={18} className="text-gradient" /> Unlimited Presentations</li>
                            <li style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><Check size={18} className="text-gradient" /> Ultra-Low Latency (Groq API)</li>
                            <li style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><Check size={18} className="text-gradient" /> Advanced Web Search RAG</li>
                        </ul>
                        
                        <Link to="/dashboard" className="btn btn-primary" style={{ width: '100%', textAlign: 'center', display: 'block' }}>Upgrade to Pro</Link>
                    </motion.div>
                </div>
            </div>
        </div>
    );
};

export default Pricing;
