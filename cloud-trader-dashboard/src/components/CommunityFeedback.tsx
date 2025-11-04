import React, { useState } from 'react';
import { User } from 'firebase/auth';

interface Comment {
  id: string;
  author: string;
  message: string;
  timestamp: string;
  avatar?: string;
}

interface CommunityFeedbackProps {
  comments: Comment[];
  onSubmit: (message: string) => void;
  user: User | null;
  loading: boolean;
  onSignIn: () => Promise<void>;
  onSignOut: () => Promise<void>;
  authEnabled: boolean;
  authError?: string | null;
}

const CommunityFeedback: React.FC<CommunityFeedbackProps> = ({ comments, onSubmit, user, loading, onSignIn, onSignOut, authEnabled, authError }) => {
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  // Input validation and sanitization
  const sanitizeInput = (input: string): string => {
    // Remove HTML tags and potentially dangerous characters
    return input
      .replace(/<[^>]*>/g, '') // Remove HTML tags
      .replace(/javascript:/gi, '') // Remove javascript: URLs
      .replace(/on\w+\s*=/gi, '') // Remove event handlers
      .replace(/[<>'"&]/g, (match) => {
        const entityMap: { [key: string]: string } = {
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

  const validateMessage = (msg: string): string => {
    const sanitized = sanitizeInput(msg);
    if (sanitized.length === 0) return 'Message cannot be empty';
    if (sanitized.length > 1000) return 'Message too long (max 1000 characters)';
    if (sanitized !== msg) return 'Invalid characters detected';
    return '';
  };

  const handleMessageChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    if (value.length <= 1000) {
      setMessage(value);
      setError('');
    } else {
      setError('Message too long (max 1000 characters)');
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const validationError = validateMessage(message);
    if (validationError) {
      setError(validationError);
      return;
    }
    if (!message.trim()) return;

    const sanitizedMessage = sanitizeInput(message);
    onSubmit(sanitizedMessage);
    setMessage('');
    setError('');
  };

  return (
    <section className="relative overflow-hidden rounded-4xl border border-white/10 bg-surface-75/80 p-6 shadow-glass">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_bottom,_rgba(239,68,68,0.14),_transparent_70%)]" />
      <div className="relative space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-amber-200/80">Community Lab</p>
            <h3 className="mt-2 text-2xl font-semibold text-white">Leave a note for the bots</h3>
            <p className="mt-2 text-sm text-slate-300">
              Share your market hunch, feedback, or experiments you&apos;d like the agents to try. Sapphire logs every whisper.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {user ? (
              <>
                <img src={user.photoURL || 'https://www.gravatar.com/avatar?d=mp'} alt="avatar" className="h-10 w-10 rounded-full border border-white/20" />
                <div className="text-xs text-right text-slate-400">
                  <p className="text-white font-semibold">{user.displayName || user.email}</p>
                  <p>Authed via Google</p>
                </div>
                <button className="rounded-full border border-white/15 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.3em] text-white/70 hover:bg-white/10" onClick={onSignOut}>Sign out</button>
              </>
            ) : (
              <button
                disabled={loading || !authEnabled}
                className="rounded-full border border-white/15 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.3em] text-white/70 transition hover:bg-white/10 disabled:opacity-40"
                onClick={onSignIn}
              >
                {authEnabled ? (loading ? 'Loading…' : 'Sign in with Google') : 'Auth offline'}
              </button>
            )}
          </div>
        </div>

        {!authEnabled && (
          <div className="rounded-3xl border border-white/10 bg-black/30 px-4 py-3 text-xs text-amber-200/80">
            Community authentication is disabled in this environment. Messages save locally only.
            {authError && <span className="mt-1 block text-[0.7rem] text-amber-100/70">{authError}</span>}
          </div>
        )}

        <form onSubmit={handleSubmit} className="rounded-3xl border border-white/10 bg-white/5 px-5 py-4 shadow-glass">
          <textarea
            value={message}
            onChange={handleMessageChange}
            placeholder={user ? 'Leave your message for the council…' : authEnabled ? 'Authenticate to send your message…' : 'Community feedback offline in this preview…'}
            className="h-24 w-full resize-none rounded-2xl border border-white/10 bg-black/20 p-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-accent-ai/50"
            disabled={!user}
            maxLength={1000}
          />
          <div className="mt-2 flex items-center justify-between">
            <div className="text-xs text-red-400">
              {error && <span>{error}</span>}
            </div>
            <div className="text-xs text-slate-400">
              {message.length}/1000
            </div>
          </div>
          <div className="mt-3 flex justify-end">
            <button
              type="submit"
              disabled={!user || !message.trim() || !!error}
              className="rounded-full bg-gradient-to-r from-accent-ai via-accent-emerald to-accent-aurora px-5 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-slate-900 disabled:opacity-40"
            >
              Submit Feedback
            </button>
          </div>
        </form>

        <div className="space-y-4">
          {comments.length === 0 ? (
            <div className="rounded-3xl border border-white/10 bg-white/5 px-5 py-5 text-center text-sm text-slate-400">
              No messages yet. Be the first to brief Sapphire!
            </div>
          ) : (
            comments.map((comment) => (
              <article key={comment.id} className="rounded-3xl border border-white/10 bg-white/5 px-5 py-4 shadow-glass">
                <div className="flex items-start gap-3">
                  <img src={comment.avatar || 'https://www.gravatar.com/avatar?d=mp'} alt="avatar" className="h-10 w-10 rounded-full border border-white/10" />
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold text-white">{comment.author}</p>
                      <time className="text-xs text-slate-400">{new Date(comment.timestamp).toLocaleString()}</time>
                    </div>
                    <p className="mt-2 text-sm text-slate-200/90 leading-relaxed">{comment.message}</p>
                  </div>
                </div>
              </article>
            ))
          )}
        </div>
      </div>
    </section>
  );
};

export default CommunityFeedback;
