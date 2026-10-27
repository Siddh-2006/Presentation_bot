const OrbBackground = () => {
    return (
        <div className="orb-background-container">
            <div className="glowing-orb orb-1"></div>
            <div className="glowing-orb orb-2"></div>
            <div className="glowing-orb orb-3"></div>

            <style>{`
                .orb-background-container {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100vw;
                    height: 100vh;
                    z-index: -1;
                    overflow: hidden;
                    background: var(--bg-primary);
                    pointer-events: none;
                }
                
                .glowing-orb {
                    position: absolute;
                    border-radius: 50%;
                    filter: blur(100px);
                    opacity: 0.6;
                    animation: floatOrb 20s infinite alternate ease-in-out;
                }

                .orb-1 {
                    width: 400px;
                    height: 400px;
                    background: var(--accent-purple);
                    top: -100px;
                    left: -100px;
                    animation-delay: 0s;
                }

                .orb-2 {
                    width: 300px;
                    height: 300px;
                    background: var(--accent-cyan);
                    bottom: -50px;
                    right: -50px;
                    animation-delay: -5s;
                }

                .orb-3 {
                    width: 250px;
                    height: 250px;
                    background: var(--accent-blue);
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    animation-delay: -10s;
                }

                @keyframes floatOrb {
                    0% {
                        transform: translate(0, 0) scale(1);
                    }
                    33% {
                        transform: translate(30px, -50px) scale(1.1);
                    }
                    66% {
                        transform: translate(-20px, 20px) scale(0.9);
                    }
                    100% {
                        transform: translate(0, 0) scale(1);
                    }
                }
            `}</style>
        </div>
    );
};

export default OrbBackground;
