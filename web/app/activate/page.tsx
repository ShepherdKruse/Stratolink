'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { QrCode, Rocket } from 'lucide-react';

export default function ActivateLandingPage() {
    const router = useRouter();
    const [deviceId, setDeviceId] = useState('');
    const [error, setError] = useState('');

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        
        if (!deviceId.trim()) {
            setError('Please enter a device ID');
            return;
        }

        // Validate device ID format (basic check)
        const deviceIdPattern = /^[a-zA-Z0-9-_]+$/;
        if (!deviceIdPattern.test(deviceId.trim())) {
            setError('Invalid device ID format');
            return;
        }

        // Navigate to activation wizard
        router.push(`/activate/${encodeURIComponent(deviceId.trim())}`);
    };

    return (
        <div className="min-h-screen bg-[#1a1a1a] text-[#e5e5e5]">
            <div className="container mx-auto px-4 py-16">
                <div className="max-w-2xl mx-auto">
                    {/* Header */}
                    <div className="text-center mb-12">
                        <div className="inline-flex items-center justify-center w-20 h-20 bg-[#4a90d9]/20 rounded-full mb-6">
                            <Rocket className="w-10 h-10 text-[#4a90d9]" />
                        </div>
                        <h1 className="text-3xl font-semibold text-[#e5e5e5] mb-3">Device Activation</h1>
                        <p className="text-[#666] text-sm">
                            Register your Stratolink device to begin tracking on the dashboard
                        </p>
                    </div>

                    {/* Activation Options */}
                    <div className="grid md:grid-cols-2 gap-6 mb-8">
                        {/* QR Code Option */}
                        <div className="bg-[#141414] border border-[#333] rounded-lg p-6">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="w-10 h-10 bg-[#4a90d9]/20 rounded-lg flex items-center justify-center">
                                    <QrCode className="w-6 h-6 text-[#4a90d9]" />
                                </div>
                                <h2 className="text-lg font-semibold text-[#e5e5e5]">Scan QR Code</h2>
                            </div>
                            <p className="text-[#666] text-sm mb-4">
                                Use your phone's camera to scan the QR code on your device label
                            </p>
                            <p className="text-[#999] text-xs font-mono">
                                Most phones can scan QR codes directly from the camera app
                            </p>
                        </div>

                        {/* Manual Entry Option */}
                        <div className="bg-[#141414] border border-[#333] rounded-lg p-6">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="w-10 h-10 bg-[#4a90d9]/20 rounded-lg flex items-center justify-center">
                                    <Rocket className="w-6 h-6 text-[#4a90d9]" />
                                </div>
                                <h2 className="text-lg font-semibold text-[#e5e5e5]">Enter Device ID</h2>
                            </div>
                            <p className="text-[#666] text-sm mb-4">
                                Manually enter your device ID if you don't have a QR code
                            </p>
                            <form onSubmit={handleSubmit} className="space-y-4">
                                <div>
                                    <label className="block text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">
                                        Device ID
                                    </label>
                                    <input
                                        type="text"
                                        value={deviceId}
                                        onChange={(e) => {
                                            setDeviceId(e.target.value);
                                            setError('');
                                        }}
                                        placeholder="e.g., balloon-001"
                                        className="w-full bg-[#1a1a1a] border border-[#333] px-4 py-3 font-mono text-[14px] text-[#e5e5e5] focus:outline-none focus:border-[#4a90d9] transition-colors rounded"
                                    />
                                    {error && (
                                        <p className="text-[#c44] text-xs mt-2">{error}</p>
                                    )}
                                </div>
                                <button
                                    type="submit"
                                    className="w-full bg-[#4a90d9] hover:bg-[#4a90d9]/90 py-3 text-sm font-semibold border border-[#4a90d9] transition-colors rounded"
                                >
                                    Continue to Activation
                                </button>
                            </form>
                        </div>
                    </div>

                    {/* Instructions */}
                    <div className="bg-[#141414] border border-[#333] rounded-lg p-6">
                        <h3 className="text-sm font-semibold text-[#e5e5e5] mb-3">What You'll Need</h3>
                        <ul className="space-y-2 text-sm text-[#999]">
                            <li className="flex items-start gap-2">
                                <span className="text-[#4a90d9] mt-1">•</span>
                                <span>Your device ID (found on device label or packaging)</span>
                            </li>
                            <li className="flex items-start gap-2">
                                <span className="text-[#4a90d9] mt-1">•</span>
                                <span>6-digit activation PIN (found on device label)</span>
                            </li>
                            <li className="flex items-start gap-2">
                                <span className="text-[#4a90d9] mt-1">•</span>
                                <span>Device powered on and ready</span>
                            </li>
                            <li className="flex items-start gap-2">
                                <span className="text-[#4a90d9] mt-1">•</span>
                                <span>Location services enabled (for GPS lock)</span>
                            </li>
                        </ul>
                    </div>

                    {/* Help Text */}
                    <div className="mt-8 text-center">
                        <p className="text-[#666] text-xs">
                            Need help? Contact support or check the{' '}
                            <a href="/docs" className="text-[#4a90d9] hover:underline">
                                documentation
                            </a>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
