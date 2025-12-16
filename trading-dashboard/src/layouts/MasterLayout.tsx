import React from 'react';

interface MasterLayoutProps {
    children: React.ReactNode;
}

export const MasterLayout: React.FC<MasterLayoutProps> = ({ children }) => {
    return (
        <div className="min-h-screen bg-[#050508] text-white font-sans">
            {/* Background gradient */}
            <div className="fixed inset-0 z-0 pointer-events-none">
                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-blue-900/15 via-[#050508] to-[#050508]" />
            </div>

            {/* Main Content - Full width, clean layout */}
            <main className="relative z-10 min-h-screen">
                <div className="max-w-[1800px] mx-auto p-6 lg:p-8">
                    {children}
                </div>
            </main>
        </div>
    );
};
