import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquare,
  Target,
  Terminal,
  Network,
  Menu,
  X,
  Settings,
  Bell,
  BarChart3,
  Briefcase,
  Cpu
} from 'lucide-react';
import { AboutModal } from '../components/AboutModal';

interface AppShellProps {
  children: React.ReactNode;
  connectionStatus: 'connected' | 'disconnected' | 'connecting';
}

export const AppShell: React.FC<AppShellProps> = ({ children, connectionStatus }) => {
  const [aboutOpen, setAboutOpen] = useState(false);
  const location = useLocation();

  // Listen for custom event from CommandDock if needed, or just let global state handle it.
  // For now, we'll expose a global event listener for 'open-about' if we want the dock to trigger it
  // But since Dock is outside AppShell in MasterLayout, we might need a Context.
  // Actually, AppShell is inside MasterLayout? No, MasterLayout wraps Routes.
  // AppShell wraps specific page content?
  // Checking App.tsx: MasterLayout wraps Routes. Routes render Pages.
  // Pages might utilize AppShell?
  // If AppShell was providing the Sidebar, and now MasterLayout provides the Dock...
  // Then AppShell might just be a layout wrapper for content styling.

  // Let's keep AppShell simple for now.

  return (
    <div className="flex flex-col h-full w-full bg-transparent text-white font-sans">
      <AboutModal open={aboutOpen} onClose={() => setAboutOpen(false)} />

      {/* 🖥️ MAIN CONTENT */}
      <main className="flex-1 relative w-full h-full">
        {children}
      </main>
    </div>
  );
};
