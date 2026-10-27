import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LogIn, LayoutDashboard, Bot } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const Navbar = () => {
    const [isScrolled, setIsScrolled] = useState(false);
    const [isLoggedIn, setIsLoggedIn] = useState(false);
    const location = useLocation();

    useEffect(() => {
        const handleScroll = () => {
            setIsScrolled(window.scrollY > 20);
        };
        window.addEventListener('scroll', handleScroll);
        return () => window.removeEventListener('scroll', handleScroll);
    }, []);

    useEffect(() => {
        setIsLoggedIn(!!localStorage.getItem('access_token'));
    }, [location]);

    return (
        <nav className={`navbar ${isScrolled ? 'scrolled' : ''}`}>
            <div className="container nav-container">
                <Link to="/" className="nav-logo">
                    <Bot size={32} className="text-gradient" />
                    <span>Voxis<span className="text-gradient">.ai</span></span>
                </Link>
                <div className="nav-links">
                    <Link to="/features">Features</Link>
                    <Link to="/use-cases">Use Cases</Link>
                    <Link to="/pricing">Pricing</Link>
                    
                    <Link to="/dashboard" className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '8px', textDecoration: 'none' }}>
                        <LayoutDashboard size={18} />
                        Dashboard
                    </Link>
                    {!isLoggedIn && (
                        <a href={`${API_BASE}/auth/login`} className="btn btn-outline" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <LogIn size={18} />
                            Google Login
                        </a>
                    )}
                </div>
            </div>
        </nav>
    );
};

export default Navbar;
