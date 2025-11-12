import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
const MAX_LENGTH = 1000;
const sanitizeInput = (input) => input
    .replace(/<[^>]*>/g, '')
    .replace(/javascript:/gi, '')
    .replace(/on\w+\s*=/gi, '')
    .replace(/[<>'"&]/g, (match) => {
    const entityMap = {
        '<': '&lt;',
        '>': '&gt;',
        "'": '&#39;',
        '"': '&quot;',
        '&': '&amp;',
    };
    return entityMap[match];
})
    .trim();
const CommunityFeedback = ({ comments, onSubmit, user, loading, onSignOut, authEnabled, authError, onSocialSignIn, onEmailSignIn, onEmailSignUp, commentSubmitting = false, }) => {
    const [message, setMessage] = useState('');
    const [inputError, setInputError] = useState('');
    const [authMode, setAuthMode] = useState('signin');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [authMessage, setAuthMessage] = useState(null);
    const [submitError, setSubmitError] = useState(null);
    const validateMessage = (value) => {
        const sanitized = sanitizeInput(value);
        if (sanitized.length === 0)
            return 'Message cannot be empty';
        if (sanitized.length > MAX_LENGTH)
            return 'Message too long (max 1000 characters)';
        if (sanitized !== value.trim())
            return 'Invalid characters detected';
        return '';
    };
    const handleMessageChange = (event) => {
        const value = event.target.value;
        if (value.length <= MAX_LENGTH) {
            setMessage(value);
            setInputError('');
        }
    };
    const handleSubmit = async (event) => {
        event.preventDefault();
        const validationError = validateMessage(message);
        if (validationError) {
            setInputError(validationError);
            return;
        }
        if (!user) {
            setInputError('Sign in to share feedback');
            return;
        }
        try {
            const sanitizedMessage = sanitizeInput(message);
            await onSubmit(sanitizedMessage);
            setMessage('');
            setInputError('');
            setSubmitError(null);
        }
        catch (error) {
            setSubmitError(error instanceof Error ? error.message : 'Failed to submit feedback');
        }
    };
    const handleEmailAuth = async (event) => {
        event.preventDefault();
        if (!authEnabled)
            return;
        try {
            if (authMode === 'signup') {
                await onEmailSignUp(email, password, displayName || undefined);
                setAuthMessage('Account created. Welcome aboard!');
            }
            else {
                await onEmailSignIn(email, password);
                setAuthMessage('Signed in successfully. Ready to contribute.');
            }
            setEmail('');
            setPassword('');
            setDisplayName('');
        }
        catch (authErr) {
            setAuthMessage(authErr instanceof Error ? authErr.message : 'Authentication failed');
        }
    };
    return (_jsxs("section", { className: "relative overflow-hidden rounded-4xl border border-white/10 bg-brand-abyss/80 p-6 shadow-sapphire-lg", children: [_jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_bottom,_rgba(59,130,246,0.14),_transparent_70%)]" }), _jsxs("div", { className: "relative space-y-6", children: [_jsxs("header", { className: "flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between", children: [_jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-brand-accent-purple/80", children: "Community Lab" }), _jsx("h3", { className: "mt-2 text-2xl font-semibold text-white", children: "Leave a note for the bots" }), _jsx("p", { className: "mt-2 text-sm text-brand-ice/80", children: "Share your market hunch, feedback, or prompts you want our agents to explore. Signals are anonymized before bots consume them." })] }), _jsx("div", { className: "flex flex-col items-end gap-2 text-xs text-brand-ice/70", children: user ? (_jsxs("div", { className: "flex items-center gap-2", children: [_jsx("img", { src: user.photoURL || 'https://www.gravatar.com/avatar?d=mp', alt: "avatar", className: "h-10 w-10 rounded-full border border-white/20" }), _jsxs("div", { className: "text-right", children: [_jsx("p", { className: "text-white font-semibold", children: user.displayName || user.email }), _jsxs("p", { children: ["Anonymized as ", user.uid ? `member-${user.uid.slice(0, 6)}` : 'community member'] })] }), _jsx("button", { className: "rounded-full border border-white/15 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.3em] text-white/70 transition hover:bg-white/10", onClick: onSignOut, children: "Sign out" })] })) : (_jsxs("div", { className: "space-y-2 text-right", children: [_jsxs("div", { className: "inline-flex gap-2", children: [_jsx("button", { disabled: loading || !authEnabled, onClick: () => onSocialSignIn('google'), className: "rounded-full border border-white/15 bg-white/5 px-3 py-2 uppercase tracking-[0.3em] text-white/70 transition hover:bg-white/10 disabled:opacity-40", children: "Google" }), _jsx("button", { disabled: loading || !authEnabled, onClick: () => onSocialSignIn('apple'), className: "rounded-full border border-white/15 bg-white/5 px-3 py-2 uppercase tracking-[0.3em] text-white/70 transition hover:bg-white/10 disabled:opacity-40", children: "Apple" }), _jsx("button", { disabled: loading || !authEnabled, onClick: () => onSocialSignIn('facebook'), className: "rounded-full border border-white/15 bg-white/5 px-3 py-2 uppercase tracking-[0.3em] text-white/70 transition hover:bg-white/10 disabled:opacity-40", children: "Facebook" })] }), _jsx("p", { className: "text-[0.65rem] text-brand-ice/50", children: "Authenticate to keep your identity safe while we collect high-signal crowd insight." })] })) })] }), !authEnabled && (_jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/30 px-4 py-3 text-xs text-brand-ice/70", children: ["Community auth is disabled in this environment. Notes stay local only.", authError && _jsx("span", { className: "mt-1 block text-[0.7rem] text-brand-ice/60", children: authError })] })), !user && authEnabled && (_jsxs("div", { className: "rounded-3xl border border-white/10 bg-white/5 px-5 py-4 text-sm text-brand-ice/80", children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-brand-ice/60", children: "Secure Email Access" }), _jsxs("div", { className: "flex gap-1 text-[0.65rem]", children: [_jsx("button", { type: "button", onClick: () => { setAuthMode('signin'); setAuthMessage(null); }, className: `rounded-full px-3 py-1 ${authMode === 'signin' ? 'bg-brand-accent-blue/30 text-white' : 'bg-white/5 text-brand-ice/70'}`, children: "Sign In" }), _jsx("button", { type: "button", onClick: () => { setAuthMode('signup'); setAuthMessage(null); }, className: `rounded-full px-3 py-1 ${authMode === 'signup' ? 'bg-brand-accent-blue/30 text-white' : 'bg-white/5 text-brand-ice/70'}`, children: "Create Account" })] })] }), _jsxs("form", { className: "mt-3 grid gap-2 text-xs", onSubmit: handleEmailAuth, children: [authMode === 'signup' && (_jsxs("label", { className: "flex flex-col gap-1 text-brand-ice/70", children: ["Display Name", _jsx("input", { value: displayName, onChange: (event) => setDisplayName(event.target.value), className: "rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-brand-accent-blue/50", type: "text", maxLength: 48, autoComplete: "name" })] })), _jsxs("label", { className: "flex flex-col gap-1 text-brand-ice/70", children: ["Email", _jsx("input", { value: email, onChange: (event) => setEmail(event.target.value), className: "rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-brand-accent-blue/50", type: "email", autoComplete: "email", required: true })] }), _jsxs("label", { className: "flex flex-col gap-1 text-brand-ice/70", children: ["Password", _jsx("input", { value: password, onChange: (event) => setPassword(event.target.value), className: "rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-brand-accent-blue/50", type: "password", autoComplete: authMode === 'signup' ? 'new-password' : 'current-password', required: true, minLength: 6 })] }), _jsx("button", { type: "submit", disabled: loading || !authEnabled, className: "mt-2 inline-flex items-center justify-center rounded-full bg-brand-accent-blue/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-white transition hover:bg-brand-accent-blue disabled:opacity-40", children: authMode === 'signup' ? 'Create Account' : 'Sign In' }), authMessage && (_jsx("p", { className: "text-[0.65rem] text-brand-accent-green/80", children: authMessage }))] })] })), _jsxs("form", { onSubmit: handleSubmit, className: "rounded-3xl border border-white/10 bg-white/5 px-5 py-4 shadow-glass", children: [_jsx("textarea", { value: message, onChange: handleMessageChange, placeholder: user ? 'Leave your message for the council…' : authEnabled ? 'Authenticate to send your message…' : 'Community feedback offline in this preview…', className: "h-24 w-full resize-none rounded-2xl border border-white/10 bg-black/20 p-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-brand-accent-blue/50", disabled: !user, maxLength: MAX_LENGTH }), _jsxs("div", { className: "mt-2 flex items-center justify-between", children: [_jsx("div", { className: "text-xs text-brand-accent-orange/80", children: inputError && _jsx("span", { children: inputError }) }), _jsxs("div", { className: "text-xs text-brand-ice/60", children: [message.length, "/", MAX_LENGTH] })] }), _jsx("div", { className: "mt-3 flex justify-end", children: _jsx("button", { type: "submit", disabled: !user || !message.trim() || !!inputError || commentSubmitting, className: "rounded-full bg-gradient-to-r from-brand-accent-blue via-brand-accent-green to-brand-accent-purple px-5 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-white disabled:opacity-40", children: commentSubmitting ? 'Sending…' : 'Submit Feedback' }) }), submitError && _jsx("p", { className: "mt-2 text-xs text-red-300", children: submitError })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-white/5 px-5 py-3 text-xs text-brand-ice/60", children: ["Privacy-first: we store anonymized handles so bots can weigh sentiment without exposing identities. Notes mentioning tickers like ", _jsx("code", { children: "$SOL" }), " are surfaced to analysts and agents for optional review only."] }), _jsx("div", { className: "space-y-4", children: comments.length === 0 ? (_jsx("div", { className: "rounded-3xl border border-white/10 bg-white/5 px-5 py-5 text-center text-sm text-brand-ice/70", children: "No messages yet. Be the first to brief Sapphire!" })) : (comments.map((comment) => (_jsx("article", { className: "rounded-3xl border border-white/10 bg-white/5 px-5 py-4 shadow-glass", children: _jsxs("div", { className: "flex items-start gap-3", children: [_jsx("img", { src: comment.avatarUrl || 'https://www.gravatar.com/avatar?d=mp', alt: "avatar", className: "h-10 w-10 rounded-full border border-white/10" }), _jsxs("div", { className: "flex-1", children: [_jsxs("div", { className: "flex flex-wrap items-center justify-between gap-2", children: [_jsx("p", { className: "text-sm font-semibold text-white", children: comment.displayName }), _jsx("time", { className: "text-xs text-brand-ice/60", children: new Date(comment.createdAt).toLocaleString() })] }), _jsx("p", { className: "mt-2 text-sm text-brand-ice/90 leading-relaxed", children: comment.message }), comment.mentionedTickers.length > 0 && (_jsx("div", { className: "mt-2 flex flex-wrap gap-2 text-xs text-brand-accent-blue", children: comment.mentionedTickers.map((ticker) => (_jsxs("span", { className: "rounded-full border border-brand-accent-blue/40 bg-brand-accent-blue/10 px-2 py-1", children: ["$", ticker] }, `${comment.id}-${ticker}`))) }))] })] }) }, comment.id)))) })] })] }));
};
export default CommunityFeedback;
