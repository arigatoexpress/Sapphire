import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from 'react';
const CommunityFeedback = ({ comments, onSubmit, user, loading, onSignIn, onSignOut, authEnabled, authError }) => {
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    // Input validation and sanitization
    const sanitizeInput = (input) => {
        // Remove HTML tags and potentially dangerous characters
        return input
            .replace(/<[^>]*>/g, '') // Remove HTML tags
            .replace(/javascript:/gi, '') // Remove javascript: URLs
            .replace(/on\w+\s*=/gi, '') // Remove event handlers
            .replace(/[<>'"&]/g, (match) => {
            const entityMap = {
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#39;',
                '"': '&quot;',
                '&': '&amp;'
            };
            return entityMap[match];
        })
            .trim();
    };
    const validateMessage = (msg) => {
        const sanitized = sanitizeInput(msg);
        if (sanitized.length === 0)
            return 'Message cannot be empty';
        if (sanitized.length > 1000)
            return 'Message too long (max 1000 characters)';
        if (sanitized !== msg)
            return 'Invalid characters detected';
        return '';
    };
    const handleMessageChange = (e) => {
        const value = e.target.value;
        if (value.length <= 1000) {
            setMessage(value);
            setError('');
        }
        else {
            setError('Message too long (max 1000 characters)');
        }
    };
    const handleSubmit = (event) => {
        event.preventDefault();
        const validationError = validateMessage(message);
        if (validationError) {
            setError(validationError);
            return;
        }
        if (!message.trim())
            return;
        const sanitizedMessage = sanitizeInput(message);
        onSubmit(sanitizedMessage);
        setMessage('');
        setError('');
    };
    return (_jsxs("section", { className: "relative overflow-hidden rounded-4xl border border-white/10 bg-surface-75/80 p-6 shadow-glass", children: [_jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_bottom,_rgba(239,68,68,0.14),_transparent_70%)]" }), _jsxs("div", { className: "relative space-y-6", children: [_jsxs("div", { className: "flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between", children: [_jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-amber-200/80", children: "Community Lab" }), _jsx("h3", { className: "mt-2 text-2xl font-semibold text-white", children: "Leave a note for the bots" }), _jsx("p", { className: "mt-2 text-sm text-slate-300", children: "Share your market hunch, feedback, or experiments you'd like the agents to try. Sapphire logs every whisper." })] }), _jsx("div", { className: "flex items-center gap-2", children: user ? (_jsxs(_Fragment, { children: [_jsx("img", { src: user.photoURL || 'https://www.gravatar.com/avatar?d=mp', alt: "avatar", className: "h-10 w-10 rounded-full border border-white/20" }), _jsxs("div", { className: "text-xs text-right text-slate-400", children: [_jsx("p", { className: "text-white font-semibold", children: user.displayName || user.email }), _jsx("p", { children: "Authed via Google" })] }), _jsx("button", { className: "rounded-full border border-white/15 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.3em] text-white/70 hover:bg-white/10", onClick: onSignOut, children: "Sign out" })] })) : (_jsx("button", { disabled: loading || !authEnabled, className: "rounded-full border border-white/15 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.3em] text-white/70 transition hover:bg-white/10 disabled:opacity-40", onClick: onSignIn, children: authEnabled ? (loading ? 'Loading…' : 'Sign in with Google') : 'Auth offline' })) })] }), !authEnabled && (_jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/30 px-4 py-3 text-xs text-amber-200/80", children: ["Community authentication is disabled in this environment. Messages save locally only.", authError && _jsx("span", { className: "mt-1 block text-[0.7rem] text-amber-100/70", children: authError })] })), _jsxs("form", { onSubmit: handleSubmit, className: "rounded-3xl border border-white/10 bg-white/5 px-5 py-4 shadow-glass", children: [_jsx("textarea", { value: message, onChange: handleMessageChange, placeholder: user ? 'Leave your message for the council…' : authEnabled ? 'Authenticate to send your message…' : 'Community feedback offline in this preview…', className: "h-24 w-full resize-none rounded-2xl border border-white/10 bg-black/20 p-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-accent-ai/50", disabled: !user, maxLength: 1000 }), _jsxs("div", { className: "mt-2 flex items-center justify-between", children: [_jsx("div", { className: "text-xs text-red-400", children: error && _jsx("span", { children: error }) }), _jsxs("div", { className: "text-xs text-slate-400", children: [message.length, "/1000"] })] }), _jsx("div", { className: "mt-3 flex justify-end", children: _jsx("button", { type: "submit", disabled: !user || !message.trim() || !!error, className: "rounded-full bg-gradient-to-r from-accent-ai via-accent-emerald to-accent-aurora px-5 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-slate-900 disabled:opacity-40", children: "Submit Feedback" }) })] }), _jsx("div", { className: "space-y-4", children: comments.length === 0 ? (_jsx("div", { className: "rounded-3xl border border-white/10 bg-white/5 px-5 py-5 text-center text-sm text-slate-400", children: "No messages yet. Be the first to brief Sapphire!" })) : (comments.map((comment) => (_jsx("article", { className: "rounded-3xl border border-white/10 bg-white/5 px-5 py-4 shadow-glass", children: _jsxs("div", { className: "flex items-start gap-3", children: [_jsx("img", { src: comment.avatar || 'https://www.gravatar.com/avatar?d=mp', alt: "avatar", className: "h-10 w-10 rounded-full border border-white/10" }), _jsxs("div", { className: "flex-1", children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsx("p", { className: "text-sm font-semibold text-white", children: comment.author }), _jsx("time", { className: "text-xs text-slate-400", children: new Date(comment.timestamp).toLocaleString() })] }), _jsx("p", { className: "mt-2 text-sm text-slate-200/90 leading-relaxed", children: comment.message })] })] }) }, comment.id)))) })] })] }));
};
export default CommunityFeedback;
