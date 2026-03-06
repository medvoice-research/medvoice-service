'use client';

import Link from 'next/link';
import { MedVoiceIcon } from '@/components/icons/MedVoiceIcon';
import { usePathname, useRouter } from 'next/navigation';
import {
    LayoutDashboard,
    Upload,
    Activity,
    Users,
    MessageCircle,
    Shield,
    ChevronLeft,
    ChevronRight,
    LogOut,
} from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';
import { signOut } from '@/app/(login)/actions';

const navigation = [
    {
        name: 'Dashboard',
        href: '/dashboard',
        icon: LayoutDashboard,
        description: 'Overview & system status',
    },
    {
        name: 'Upload Consultation',
        href: '/dashboard/upload',
        icon: Upload,
        description: 'Record new consultation',
    },
    {
        name: 'My Consultations',
        href: '/dashboard/consultations',
        icon: Activity,
        description: 'Monitor workflows',
    },
    {
        name: 'Patient Records',
        href: '/dashboard/patients',
        icon: Users,
        description: 'Browse patient data',
    },
    {
        name: 'Medical Assistant',
        href: '/dashboard/chat',
        icon: MessageCircle,
        description: 'AI-powered Q&A',
    },
];

export function Sidebar() {
    const pathname = usePathname();
    const router = useRouter();
    const [collapsed, setCollapsed] = useState(false);

    const handleSignOut = async () => {
        await signOut();
        router.push('/sign-in');
    };

    return (
        <>
            {/* Mobile overlay */}
            <nav
                className={cn(
                    'hidden md:flex flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border transition-all duration-300 ease-in-out',
                    collapsed ? 'w-[68px]' : 'w-64'
                )}
            >
                {/* Logo / Brand */}
                <div className="flex items-center gap-3 px-4 py-5 border-b border-sidebar-border">
                    <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-sidebar-primary text-sidebar-primary-foreground shrink-0">
                        <MedVoiceIcon className="w-6 h-6" />
                    </div>
                    {!collapsed && (
                        <div className="overflow-hidden">
                            <h1 className="text-sm font-semibold text-sidebar-foreground truncate">
                                MedVoice
                            </h1>
                            <p className="text-xs text-sidebar-foreground/60 truncate">
                                Clinical Portal
                            </p>
                        </div>
                    )}
                </div>

                {/* Navigation */}
                <div className="flex-1 py-4 space-y-1 px-2 overflow-y-auto">
                    {navigation.map((item) => {
                        const isActive =
                            pathname === item.href ||
                            (item.href !== '/dashboard' && pathname.startsWith(item.href));

                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={cn(
                                    'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150',
                                    isActive
                                        ? 'bg-sidebar-accent text-sidebar-primary font-medium'
                                        : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground'
                                )}
                                title={collapsed ? item.name : undefined}
                            >
                                <item.icon className="w-5 h-5 shrink-0" />
                                {!collapsed && <span className="truncate">{item.name}</span>}
                            </Link>
                        );
                    })}
                </div>

                {/* HIPAA footer + Log Out + Collapse toggle */}
                <div className="border-t border-sidebar-border px-3 py-3 space-y-2">
                    {!collapsed && (
                        <div className="flex items-center gap-2 text-xs text-sidebar-foreground/40 px-1">
                            <Shield className="w-3.5 h-3.5 shrink-0" />
                            <span>HIPAA Compliant</span>
                        </div>
                    )}
                    <button
                        onClick={handleSignOut}
                        className={cn(
                            'flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm transition-all duration-150 text-sidebar-foreground/70 hover:bg-red-500/10 hover:text-red-500 cursor-pointer',
                            collapsed && 'justify-center'
                        )}
                        title={collapsed ? 'Log Out' : undefined}
                        aria-label="Log out"
                    >
                        <LogOut className="w-5 h-5 shrink-0" />
                        {!collapsed && <span>Log Out</span>}
                    </button>
                    <button
                        onClick={() => setCollapsed(!collapsed)}
                        className="flex items-center justify-center w-full py-1.5 rounded-md text-sidebar-foreground/50 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground transition-colors cursor-pointer"
                        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                    >
                        {collapsed ? (
                            <ChevronRight className="w-4 h-4" />
                        ) : (
                            <ChevronLeft className="w-4 h-4" />
                        )}
                    </button>
                </div>
            </nav>

            {/* Mobile bottom navigation */}
            <nav className="fixed bottom-0 left-0 right-0 z-50 md:hidden bg-card border-t border-border">
                <div className="flex items-center justify-around py-2 px-1">
                    {navigation.slice(0, 4).map((item) => {
                        const isActive =
                            pathname === item.href ||
                            (item.href !== '/dashboard' && pathname.startsWith(item.href));

                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={cn(
                                    'flex flex-col items-center gap-0.5 px-2 py-1.5 rounded-md text-xs transition-colors cursor-pointer',
                                    isActive
                                        ? 'text-primary font-medium'
                                        : 'text-muted-foreground'
                                )}
                            >
                                <item.icon className="w-5 h-5" />
                                <span className="truncate max-w-[60px]">
                                    {item.name.split(' ')[0]}
                                </span>
                            </Link>
                        );
                    })}
                    <button
                        onClick={handleSignOut}
                        className="flex flex-col items-center gap-0.5 px-2 py-1.5 rounded-md text-xs transition-colors cursor-pointer text-muted-foreground hover:text-red-500"
                        aria-label="Log out"
                    >
                        <LogOut className="w-5 h-5" />
                        <span className="truncate max-w-[60px]">Logout</span>
                    </button>
                </div>
            </nav>
        </>
    );
}
