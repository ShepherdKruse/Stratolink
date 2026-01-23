'use client';

import { Map, Rocket, BarChart3 } from 'lucide-react';

type Tab = 'radar' | 'missions' | 'intel';

interface BottomNavProps {
    activeTab: Tab;
    onTabChange: (tab: Tab) => void;
}

export default function BottomNav({ activeTab, onTabChange }: BottomNavProps) {
    const tabs = [
        { id: 'radar' as Tab, label: 'Radar', icon: Map },
        { id: 'missions' as Tab, label: 'Missions', icon: Rocket },
        { id: 'intel' as Tab, label: 'Intel', icon: BarChart3 },
    ];

    return (
        <nav className="fixed bottom-0 left-0 right-0 z-50 backdrop-blur-md bg-[#1a1a1a]/95 border-t border-[#333]">
            <div className="flex items-center justify-around h-16 px-2">
                {tabs.map((tab) => {
                    const Icon = tab.icon;
                    const isActive = activeTab === tab.id;
                    
                    return (
                        <button
                            key={tab.id}
                            onClick={() => onTabChange(tab.id)}
                            className={`flex flex-col items-center justify-center flex-1 h-full min-w-[44px] transition-all ${
                                isActive 
                                    ? 'text-[#4a90d9]' 
                                    : 'text-[#666]'
                            }`}
                        >
                            <div className={`relative ${isActive ? 'scale-110' : 'scale-100'} transition-transform`}>
                                <Icon size={24} strokeWidth={isActive ? 2.5 : 2} />
                                {isActive && (
                                    <div className="absolute -inset-1 bg-[#4a90d9]/20 rounded-full blur-sm" />
                                )}
                            </div>
                            <span className={`text-[10px] font-medium mt-0.5 ${isActive ? 'text-[#4a90d9]' : 'text-[#666]'}`}>
                                {tab.label}
                            </span>
                        </button>
                    );
                })}
            </div>
        </nav>
    );
}
