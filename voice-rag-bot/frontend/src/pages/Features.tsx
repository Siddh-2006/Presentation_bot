import { motion } from 'framer-motion';
import { Bot, FastForward, Globe, Shield, Smartphone, Zap } from 'lucide-react';

const Features = () => {
    return (
        <div style={{ paddingTop: '150px', paddingBottom: '100px' }}>
            <div className="container">
                <motion.div 
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8 }}
                    style={{ textAlign: 'center', marginBottom: '5rem' }}
                >
                    <h1 style={{ fontSize: '3.5rem' }}>Elite <span className="text-gradient">Capabilities</span></h1>
                    <p className="text-secondary" style={{ fontSize: '1.2rem', maxWidth: '600px', margin: '0 auto' }}>
                        Voxis.ai replaces manual clicking, reading, and stuttering with a completely autonomous pipeline.
                    </p>
                </motion.div>

                <div className="grid-3">
                    {[
                        { icon: <Zap size={32} />, title: "Groq LPU Processing", desc: "Achieve true sub-second latency for natural conversations." },
                        { icon: <FastForward size={32} />, title: "Slide Syncing", desc: "Automatically advances your PowerPoint when it finishes a topic." },
                        { icon: <Bot size={32} />, title: "Llama-3 Reasoning", desc: "Powered by Meta's most advanced open-source model." },
                        { icon: <Globe size={32} />, title: "Web-RAG Support", desc: "Pulls real-time data from the internet if your slide lacks context." },
                        { icon: <Shield size={32} />, title: "Enterprise Security", desc: "Your slide data is vectorized securely using ChromaDB." },
                        { icon: <Smartphone size={32} />, title: "Any Platform", desc: "Works flawlessly over Google Meet, Zoom, or Teams screen share." }
                    ].map((feature, i) => (
                        <motion.div 
                            key={i}
                            initial={{ opacity: 0, y: 50 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ duration: 0.5, delay: i * 0.1 }}
                            className="glass-panel"
                        >
                            <div className="text-gradient" style={{ marginBottom: '1rem' }}>{feature.icon}</div>
                            <h3>{feature.title}</h3>
                            <p className="text-secondary">{feature.desc}</p>
                        </motion.div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default Features;
