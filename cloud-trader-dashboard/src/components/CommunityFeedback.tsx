import React, { useState } from 'react';
import type { User } from 'firebase/auth';
import type { CommunityComment } from '../hooks/useCommunityComments';

type SocialProvider = 'google' | 'facebook' | 'apple';

interface CommunityFeedbackProps {
  comments: CommunityComment[];
  onSubmit: (message: string) => Promise<void>;
  user: User | null;
  loading: boolean;
  onSignOut: () => Promise<void>;
  authEnabled: boolean;
  authError?: string | null;
  onSocialSignIn: (provider: SocialProvider) => Promise<void>;
  onEmailSignIn: (email: string, password: string) => Promise<void>;
  onEmailSignUp: (email: string, password: string, displayName?: string) => Promise<void>;
  commentSubmitting?: boolean;
}

const MAX_LENGTH = 1000;

const sanitizeInput = (input: string): string =>
  input
    .replace(/<[^>]*>/g, '')
    .replace(/javascript:/gi, '')
    .replace(/on\w+\s*=/gi, '')
      .replace(/[<>'"&]/g, (match) => {
      const entityMap: Record<string, string> = {
          '<': '&lt;',
          '>': '&gt;',
          "'": '&#39;',
          '"': '&quot;',
        '&': '&amp;',
        };
        return entityMap[match];
      })
      .trim();

const CommunityFeedback: React.FC<CommunityFeedbackProps> = ({
  comments,
  onSubmit,
  user,
  loading,
  onSignOut,
  authEnabled,
  authError,
  onSocialSignIn,
  onEmailSignIn,
  onEmailSignUp,
  commentSubmitting = false,
}) => {
  const [message, setMessage] = useState('');
  const [inputError, setInputError] = useState('');
  const [authMode, setAuthMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [authMessage, setAuthMessage] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const validateMessage = (value: string): string => {
    const sanitized = sanitizeInput(value);
    if (sanitized.length === 0) return 'Message cannot be empty';
    if (sanitized.length > MAX_LENGTH) return 'Message too long (max 1000 characters)';
    if (sanitized !== value.trim()) return 'Invalid characters detected';
    return '';
  };

  const handleMessageChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = event.target.value;
    if (value.length <= MAX_LENGTH) {
      setMessage(value);
      setInputError('');
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
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
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Failed to submit feedback');
    }
  };

  const handleEmailAuth = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!authEnabled) return;
    try {
      if (authMode === 'signup') {
        await onEmailSignUp(email, password, displayName || undefined);
        setAuthMessage('Account created. Welcome aboard!');
      } else {
        await onEmailSignIn(email, password);
        setAuthMessage('Signed in successfully. Ready to contribute.');
      }
      setEmail('');
      setPassword('');
      setDisplayName('');
    } catch (authErr) {
      setAuthMessage(authErr instanceof Error ? authErr.message : 'Authentication failed');
    }
  };

  return (
    <section className="relative overflow-hidden rounded-4xl border border-white/10 bg-brand-abyss/80 p-6 shadow-sapphire-lg">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_bottom,_rgba(59,130,246,0.14),_transparent_70%)]" />
      <div className="relative space-y-6">
        <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-brand-accent-purple/80">Community Lab</p>
            <h3 className="mt-2 text-2xl font-semibold text-white">Leave a note for the bots</h3>
            <p className="mt-2 text-sm text-brand-ice/80">
              Share your market hunch, feedback, or prompts you want our agents to explore. Signals are anonymized before bots consume them.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2 text-xs text-brand-ice/70">
            {user ? (
              <div className="flex items-center gap-2">
                <img
                  src={user.photoURL || 'https://www.gravatar.com/avatar?d=mp'}
                  alt="avatar"
                  className="h-10 w-10 rounded-full border border-white/20"
                />
                <div className="text-right">
                  <p className="text-white font-semibold">{user.displayName || user.email}</p>
                  <p>Anonymized as {user.uid ? `member-${user.uid.slice(0, 6)}` : 'community member'}</p>
                </div>
                <button
                  className="rounded-full border border-white/15 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.3em] text-white/70 transition hover:bg-white/10"
                  onClick={onSignOut}
                >
                  Sign out
                </button>
              </div>
            ) : (
              <div className="space-y-2 text-right">
                <div className="inline-flex gap-2">
                  <button
                    disabled={loading || !authEnabled}
                    onClick={() => onSocialSignIn('google')}
                    className="rounded-full border border-white/15 bg-white/5 px-3 py-2 uppercase tracking-[0.3em] text-white/70 transition hover:bg-white/10 disabled:opacity-40"
                  >
                    Google
                  </button>
                  <button
                    disabled={loading || !authEnabled}
                    onClick={() => onSocialSignIn('apple')}
                    className="rounded-full border border-white/15 bg-white/5 px-3 py-2 uppercase tracking-[0.3em] text-white/70 transition hover:bg-white/10 disabled:opacity-40"
                  >
                    Apple
                  </button>
              <button
                disabled={loading || !authEnabled}
                    onClick={() => onSocialSignIn('facebook')}
                    className="rounded-full border border-white/15 bg-white/5 px-3 py-2 uppercase tracking-[0.3em] text-white/70 transition hover:bg-white/10 disabled:opacity-40"
              >
                    Facebook
              </button>
                </div>
                <p className="text-[0.65rem] text-brand-ice/50">
                  Authenticate to keep your identity safe while we collect high-signal crowd insight.
                </p>
              </div>
            )}
          </div>
        </header>

        {!authEnabled && (
          <div className="rounded-3xl border border-white/10 bg-black/30 px-4 py-3 text-xs text-brand-ice/70">
            Community auth is disabled in this environment. Notes stay local only.
            {authError && <span className="mt-1 block text-[0.7rem] text-brand-ice/60">{authError}</span>}
          </div>
        )}

        {!user && authEnabled && (
          <div className="rounded-3xl border border-white/10 bg-white/5 px-5 py-4 text-sm text-brand-ice/80">
            <div className="flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.3em] text-brand-ice/60">Secure Email Access</p>
              <div className="flex gap-1 text-[0.65rem]">
                <button
                  type="button"
                  onClick={() => { setAuthMode('signin'); setAuthMessage(null); }}
                  className={`rounded-full px-3 py-1 ${authMode === 'signin' ? 'bg-brand-accent-blue/30 text-white' : 'bg-white/5 text-brand-ice/70'}`}
                >
                  Sign In
                </button>
                <button
                  type="button"
                  onClick={() => { setAuthMode('signup'); setAuthMessage(null); }}
                  className={`rounded-full px-3 py-1 ${authMode === 'signup' ? 'bg-brand-accent-blue/30 text-white' : 'bg-white/5 text-brand-ice/70'}`}
                >
                  Create Account
                </button>
              </div>
            </div>

            <form className="mt-3 grid gap-2 text-xs" onSubmit={handleEmailAuth}>
              {authMode === 'signup' && (
                <label className="flex flex-col gap-1 text-brand-ice/70">
                  Display Name
                  <input
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    className="rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-brand-accent-blue/50"
                    type="text"
                    maxLength={48}
                    autoComplete="name"
                  />
                </label>
              )}
              <label className="flex flex-col gap-1 text-brand-ice/70">
                Email
                <input
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-brand-accent-blue/50"
                  type="email"
                  autoComplete="email"
                  required
                />
              </label>
              <label className="flex flex-col gap-1 text-brand-ice/70">
                Password
                <input
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-brand-accent-blue/50"
                  type="password"
                  autoComplete={authMode === 'signup' ? 'new-password' : 'current-password'}
                  required
                  minLength={6}
                />
              </label>
              <button
                type="submit"
                disabled={loading || !authEnabled}
                className="mt-2 inline-flex items-center justify-center rounded-full bg-brand-accent-blue/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-white transition hover:bg-brand-accent-blue disabled:opacity-40"
              >
                {authMode === 'signup' ? 'Create Account' : 'Sign In'}
              </button>
              {authMessage && (
                <p className="text-[0.65rem] text-brand-accent-green/80">{authMessage}</p>
              )}
            </form>
          </div>
        )}

        <form onSubmit={handleSubmit} className="rounded-3xl border border-white/10 bg-white/5 px-5 py-4 shadow-glass">
          <textarea
            value={message}
            onChange={handleMessageChange}
            placeholder={user ? 'Leave your message for the council…' : authEnabled ? 'Authenticate to send your message…' : 'Community feedback offline in this preview…'}
            className="h-24 w-full resize-none rounded-2xl border border-white/10 bg-black/20 p-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-brand-accent-blue/50"
            disabled={!user}
            maxLength={MAX_LENGTH}
          />
          <div className="mt-2 flex items-center justify-between">
            <div className="text-xs text-brand-accent-orange/80">
              {inputError && <span>{inputError}</span>}
            </div>
            <div className="text-xs text-brand-ice/60">
              {message.length}/{MAX_LENGTH}
            </div>
          </div>
          <div className="mt-3 flex justify-end">
            <button
              type="submit"
              disabled={!user || !message.trim() || !!inputError || commentSubmitting}
              className="rounded-full bg-gradient-to-r from-brand-accent-blue via-brand-accent-green to-brand-accent-purple px-5 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-white disabled:opacity-40"
            >
              {commentSubmitting ? 'Sending…' : 'Submit Feedback'}
            </button>
          </div>
          {submitError && <p className="mt-2 text-xs text-red-300">{submitError}</p>}
        </form>

        <div className="rounded-3xl border border-white/10 bg-white/5 px-5 py-3 text-xs text-brand-ice/60">
          Privacy-first: we store anonymized handles so bots can weigh sentiment without exposing identities. Notes mentioning tickers like <code>$SOL</code> are surfaced to analysts and agents for optional review only.
        </div>

        <div className="space-y-4">
          {comments.length === 0 ? (
            <div className="rounded-3xl border border-white/10 bg-white/5 px-5 py-5 text-center text-sm text-brand-ice/70">
              No messages yet. Be the first to brief Sapphire!
            </div>
          ) : (
            comments.map((comment) => (
              <article key={comment.id} className="rounded-3xl border border-white/10 bg-white/5 px-5 py-4 shadow-glass">
                <div className="flex items-start gap-3">
                  <img
                    src={comment.avatarUrl || 'https://www.gravatar.com/avatar?d=mp'}
                    alt="avatar"
                    className="h-10 w-10 rounded-full border border-white/10"
                  />
                  <div className="flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-white">{comment.displayName}</p>
                      <time className="text-xs text-brand-ice/60">{new Date(comment.createdAt).toLocaleString()}</time>
                    </div>
                    <p className="mt-2 text-sm text-brand-ice/90 leading-relaxed">{comment.message}</p>
                    {comment.mentionedTickers.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-brand-accent-blue">
                        {comment.mentionedTickers.map((ticker: string) => (
                          <span key={`${comment.id}-${ticker}`} className="rounded-full border border-brand-accent-blue/40 bg-brand-accent-blue/10 px-2 py-1">
                            ${ticker}
                          </span>
                        ))}
                      </div>
                    )}
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
