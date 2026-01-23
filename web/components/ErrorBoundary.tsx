'use client';

import React from 'react';

interface ErrorBoundaryState {
    hasError: boolean;
    error?: Error;
}

interface ErrorBoundaryProps {
    children: React.ReactNode;
    fallback?: React.ReactNode;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
        console.error('ErrorBoundary caught an error:', error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback;
            }
            
            return (
                <div className="flex items-center justify-center h-screen bg-[#1a1a1a] text-[#e5e5e5]">
                    <div className="text-center p-8">
                        <p className="text-[#666] text-sm mb-2">Unable to load dashboard</p>
                        <button
                            onClick={() => window.location.reload()}
                            className="text-[#4a90d9] text-xs hover:underline"
                        >
                            Reload
                        </button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
