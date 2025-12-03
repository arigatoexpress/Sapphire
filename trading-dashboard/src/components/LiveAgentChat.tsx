import React, { useRef, useEffect } from 'react';
import { MessageSquare, Bot, Brain, Zap, Clock, User } from 'lucide-react';
import { format } from 'date-fns';

interface ChatMessage {
  id: string;
  agentId: string;
  agentName: string;
  role: string;
  content: string;
  timestamp: string;
  tags?: string[];
  sentiment?: 'positive' | 'negative' | 'neutral';
  relatedSymbol?: string;
}

interface Props {
  messages: ChatMessage[];
}

export const LiveAgentChat: React.FC<Props> = ({ messages }) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div className="flex flex-col h-full bg-transparent overflow-hidden">
      <div className="p-4 border-b border-white/5 flex items-center justify-between bg-black/20">
        <div className="flex items-center gap-2">
          <MessageSquare className="text-purple-400" size={16} />
          <h3 className="font-bold text-xs uppercase tracking-wider text-white/70">Consensus Stream</h3>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
          </span>
          <span className="text-[10px] text-green-500 font-mono">LIVE</span>
        </div>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-4 scroll-smooth custom-scrollbar"
      >
        {(!messages || messages.length === 0) ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-500 gap-3">
            <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center animate-pulse">
              <Bot size={24} className="text-slate-600" />
            </div>
            <p className="text-xs font-mono">ESTABLISHING UPLINK...</p>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))
        )}
      </div>
    </div>
  );
};

const MessageBubble = ({ message }: { message: ChatMessage }) => {
  const isSystem = message.agentId === 'system';
  const isGrok = message.agentId.includes('grok');
  
  // Determine color scheme based on agent type
  let roleColor = "text-slate-400 border-slate-700 bg-slate-800";
  let contentBg = "bg-white/5 border-white/5 text-slate-200";
  
  if (isGrok) {
    roleColor = "text-purple-300 border-purple-500/30 bg-purple-500/10";
    contentBg = "bg-purple-500/5 border-purple-500/10 text-purple-100";
  } else if (message.role === 'OBSERVATION') {
    roleColor = "text-blue-300 border-blue-500/30 bg-blue-500/10";
  } else if (message.role === 'CRITIQUE' || message.role === 'RISK') {
    roleColor = "text-rose-300 border-rose-500/30 bg-rose-500/10";
    contentBg = "bg-rose-500/5 border-rose-500/10 text-rose-100";
  } else if (message.role === 'EXECUTION') {
    roleColor = "text-green-300 border-green-500/30 bg-green-500/10";
    contentBg = "bg-green-500/5 border-green-500/10 text-green-100";
  }

  return (
    <div className={`flex gap-3 ${isSystem ? 'justify-center my-2 opacity-70' : 'justify-start animate-fadeInUp'}`}>
      {!isSystem && (
        <div className={`flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center mt-1 border ${roleColor.split(' ')[1]} ${roleColor.split(' ')[2]}`}>
          {getAgentIcon(message.agentId)}
        </div>
      )}

      <div className={`flex flex-col max-w-[90%] ${isSystem ? 'items-center w-full' : ''}`}>
        {!isSystem && (
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-[10px] font-bold ${isGrok ? 'text-purple-300' : 'text-slate-300'}`}>{message.agentName}</span>
            <span className={`text-[9px] px-1.5 py-0.5 rounded border uppercase tracking-wide ${roleColor}`}>
              {message.role}
            </span>
            <span className="text-[9px] text-slate-500 flex items-center gap-1 font-mono ml-auto">
              {format(new Date(message.timestamp), 'HH:mm:ss')}
            </span>
          </div>
        )}

        <div
          className={`
            px-3 py-2 rounded-2xl text-xs leading-relaxed backdrop-blur-sm border
            ${isSystem
              ? 'bg-white/5 text-slate-400 text-[10px] py-1 px-3 rounded-full border-white/5 font-mono uppercase tracking-wider'
              : `${contentBg} rounded-tl-none`
            }
          `}
        >
          {message.content}
        </div>

        {!isSystem && message.relatedSymbol && (
           <div className="flex gap-1 mt-1">
              <span className="px-1.5 py-0.5 rounded-md bg-white/5 border border-white/10 text-[9px] text-slate-400 font-mono">
                ${message.relatedSymbol}
              </span>
           </div>
        )}
      </div>
    </div>
  );
};

function getAgentIcon(agentId: string) {
  if (agentId.includes('grok')) return <Brain size={14} className="text-purple-400" />;
  if (agentId.includes('trend') || agentId.includes('momentum')) return <Zap size={14} className="text-blue-400" />;
  if (agentId.includes('sentiment')) return <MessageSquare size={14} className="text-amber-400" />;
  if (agentId.includes('risk')) return <ShieldIcon className="w-3.5 h-3.5 text-rose-400" />;
  return <Bot size={14} className="text-slate-400" />;
}

const ShieldIcon = ({ className }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);
