'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import confetti from 'canvas-confetti';
import { activateDevice } from '@/lib/actions/activate';
import Map, { Marker } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';

interface PageProps {
    params: Promise<{
        deviceId: string;
    }>;
}

const slideVariants = {
    enter: (direction: number) => ({
        x: direction > 0 ? 1000 : -1000,
        opacity: 0,
    }),
    center: {
        x: 0,
        opacity: 1,
    },
    exit: (direction: number) => ({
        x: direction < 0 ? 1000 : -1000,
        opacity: 0,
    }),
};

export default function ActivatePage({ params }: PageProps) {
    const router = useRouter();
    const [deviceId, setDeviceId] = useState<string>('');
    const [step, setStep] = useState(1);
    const [direction, setDirection] = useState(1);
    const [pin, setPin] = useState('');
    const [name, setName] = useState('');
    const [ledConfirmed, setLedConfirmed] = useState(false);
    const [location, setLocation] = useState<{ lat: number; lon: number } | null>(null);
    const [locationName, setLocationName] = useState<string>('');
    const [locationError, setLocationError] = useState<string>('');
    const [isHolding, setIsHolding] = useState(false);
    const [holdProgress, setHoldProgress] = useState(0);
    const [isActivating, setIsActivating] = useState(false);
    const holdIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const progressIntervalRef = useRef<NodeJS.Timeout | null>(null);

    // Resolve params promise
    useEffect(() => {
        params.then((resolvedParams) => {
            setDeviceId(resolvedParams.deviceId);
        });
    }, [params]);

    // Step 1: PIN and Name validation
    const canProceedFromStep1 = pin.length === 6 && name.trim().length > 0;

    // Step 2: LED confirmation
    const canProceedFromStep2 = ledConfirmed;

    // Step 3: Location lock
    const canProceedFromStep3 = location !== null && locationName !== '';

    // Get location on Step 3 mount
    useEffect(() => {
        if (step === 3 && !location) {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    async (position) => {
                        const lat = position.coords.latitude;
                        const lon = position.coords.longitude;
                        setLocation({ lat, lon });

                        // Reverse geocode using Mapbox
                        try {
                            const response = await fetch(
                                `https://api.mapbox.com/geocoding/v5/mapbox.places/${lon},${lat}.json?access_token=${process.env.NEXT_PUBLIC_MAPBOX_TOKEN}&types=place,locality,neighborhood`
                            );
                            const data = await response.json();
                            if (data.features && data.features.length > 0) {
                                const placeName = data.features[0].place_name;
                                setLocationName(placeName);
                            } else {
                                setLocationName(`${lat.toFixed(4)}, ${lon.toFixed(4)}`);
                            }
                        } catch (error) {
                            console.error('Geocoding error:', error);
                            setLocationName(`${lat.toFixed(4)}, ${lon.toFixed(4)}`);
                        }
                    },
                    (error) => {
                        setLocationError('Unable to get location. Please enable location services.');
                        console.error('Geolocation error:', error);
                    }
                );
            } else {
                setLocationError('Geolocation is not supported by your browser.');
            }
        }
    }, [step]);

    // Handle hold-to-launch button
    const handleMouseDown = () => {
        setIsHolding(true);
        setHoldProgress(0);

        // Progress animation
        progressIntervalRef.current = setInterval(() => {
            setHoldProgress((prev) => {
                if (prev >= 100) {
                    return 100;
                }
                return prev + (100 / 30); // 3 seconds = 30 intervals at ~100ms each
            });
        }, 100);

        // Complete after 3 seconds
        holdIntervalRef.current = setTimeout(() => {
            handleLaunch();
        }, 3000);
    };

    const handleMouseUp = () => {
        if (holdIntervalRef.current) {
            clearTimeout(holdIntervalRef.current);
        }
        if (progressIntervalRef.current) {
            clearInterval(progressIntervalRef.current);
        }
        setIsHolding(false);
        setHoldProgress(0);
    };

    const handleLaunch = async () => {
        if (!location || isActivating) return;

        setIsActivating(true);

        // Trigger confetti
        confetti({
            particleCount: 100,
            spread: 70,
            origin: { y: 0.6 },
        });

        // Call server action
        const result = await activateDevice(
            deviceId,
            pin,
            name,
            location.lat,
            location.lon
        );

        if (result.success) {
            // Small delay to show confetti
            setTimeout(() => {
                router.push(`/dashboard?mode=ride_along&balloon=${deviceId}`);
            }, 1000);
        } else {
            // Show error in a more user-friendly way
            const errorMessage = result.error || 'Launch failed';
            setIsActivating(false);
            setIsHolding(false);
            setHoldProgress(0);
            
            // Show error with helpful context
            alert(`Activation Failed\n\n${errorMessage}\n\n${errorMessage.includes('Device not found') ? 'Note: In development mode, devices should be auto-created. If you see this error, check the browser console for details.' : ''}`);
        }
    };

    const nextStep = () => {
        setDirection(1);
        setStep((prev) => prev + 1);
    };

    const prevStep = () => {
        setDirection(-1);
        setStep((prev) => prev - 1);
    };

    return (
        <div className="min-h-screen bg-[#1a1a1a] text-[#e5e5e5]">
            {/* Progress Indicator */}
            <div className="fixed top-0 left-0 right-0 h-px bg-[#333] z-50">
                <div
                    className="h-full bg-[#4a90d9] transition-all duration-300"
                    style={{ width: `${(step / 4) * 100}%` }}
                />
            </div>

            {/* Step Counter */}
            <div className="fixed top-3 right-3 z-40">
                <div className="bg-[#1a1a1a]/95 backdrop-blur-md border border-[#333] px-3 py-1.5">
                    <span className="text-[10px] font-mono text-[#666] uppercase tracking-wider">
                        Step {step} / 4
                    </span>
                </div>
            </div>

            <div className="container mx-auto px-4 py-12 pt-16">
                <AnimatePresence mode="wait" custom={direction}>
                    <motion.div
                        key={step}
                        custom={direction}
                        variants={slideVariants}
                        initial="enter"
                        animate="center"
                        exit="exit"
                        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                        className="max-w-md mx-auto"
                    >
                        {/* Step 1: Identity */}
                        {step === 1 && (
                            <div className="space-y-6">
                                <div className="border-b border-[#333] pb-4">
                                    <h1 className="text-[18px] font-semibold text-[#e5e5e5] mb-1">Device Activation</h1>
                                    <p className="text-[11px] text-[#666] font-mono">Enter activation credentials</p>
                                </div>

                                <div className="space-y-4">
                                    <div>
                                        <label className="block text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">
                                            Device ID
                                        </label>
                                        <div className="bg-[#141414] border border-[#333] px-3 py-2 font-mono text-[12px] text-[#4a90d9]">
                                            {deviceId || 'Loading...'}
                                        </div>
                                    </div>

                                    <div>
                                        <label className="block text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">
                                            Activation PIN
                                        </label>
                                        <input
                                            type="text"
                                            inputMode="numeric"
                                            maxLength={6}
                                            value={pin}
                                            onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
                                            className="w-full bg-[#141414] border border-[#333] px-4 py-3 font-mono text-[20px] text-center tracking-widest text-[#e5e5e5] focus:outline-none focus:border-[#4a90d9] transition-colors"
                                            placeholder="000000"
                                        />
                                    </div>

                                    <div>
                                        <label className="block text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-2">
                                            Mission Commander
                                        </label>
                                        <input
                                            type="text"
                                            value={name}
                                            onChange={(e) => setName(e.target.value)}
                                            className="w-full bg-[#141414] border border-[#333] px-3 py-2 text-[12px] text-[#e5e5e5] focus:outline-none focus:border-[#4a90d9] transition-colors"
                                            placeholder="Your name"
                                        />
                                    </div>
                                </div>

                                <button
                                    onClick={nextStep}
                                    disabled={!canProceedFromStep1}
                                    className="w-full bg-[#4a90d9] hover:bg-[#4a90d9]/90 disabled:bg-[#333] disabled:text-[#666] disabled:cursor-not-allowed py-3 text-[12px] font-mono font-semibold border border-[#4a90d9] disabled:border-[#333] transition-colors min-h-[44px]"
                                >
                                    Continue
                                </button>
                            </div>
                        )}

                        {/* Step 2: Hardware Verification */}
                        {step === 2 && (
                            <div className="space-y-6">
                                <div className="border-b border-[#333] pb-4">
                                    <h1 className="text-[18px] font-semibold text-[#e5e5e5] mb-1">Hardware Verification</h1>
                                    <p className="text-[11px] text-[#666] font-mono">Confirm device power state</p>
                                </div>

                                <div className="flex flex-col items-center space-y-6">
                                    {/* Animated Switch */}
                                    <div className="relative w-24 h-12">
                                        <motion.div
                                            animate={{
                                                scale: [1, 1.05, 1],
                                            }}
                                            transition={{
                                                duration: 1.5,
                                                repeat: Infinity,
                                                ease: 'easeInOut',
                                            }}
                                            className="absolute inset-0 bg-[#141414] rounded-full border border-[#333]"
                                        />
                                        <motion.div
                                            animate={{
                                                x: [0, 48, 0],
                                            }}
                                            transition={{
                                                duration: 1.5,
                                                repeat: Infinity,
                                                ease: 'easeInOut',
                                            }}
                                            className="absolute top-0.5 left-0.5 w-11 h-11 bg-[#4a9] rounded-full"
                                        />
                                    </div>

                                    <div className="text-center space-y-3">
                                        <p className="text-[12px] font-semibold text-[#e5e5e5] font-mono">Power Switch ON</p>
                                        <p className="text-[11px] text-[#666] font-mono">Do you see the Green LED flashing?</p>
                                    </div>

                                    <div className="flex gap-3 w-full">
                                        <button
                                            onClick={() => {
                                                setLedConfirmed(false);
                                                prevStep();
                                            }}
                                            className="flex-1 bg-[#141414] border border-[#333] hover:border-[#666] py-3 text-[12px] font-mono font-semibold text-[#999] hover:text-[#e5e5e5] transition-colors min-h-[44px]"
                                        >
                                            No
                                        </button>
                                        <button
                                            onClick={() => {
                                                setLedConfirmed(true);
                                                nextStep();
                                            }}
                                            className="flex-1 bg-[#4a90d9] hover:bg-[#4a90d9]/90 border border-[#4a90d9] py-3 text-[12px] font-mono font-semibold text-[#e5e5e5] transition-colors min-h-[44px]"
                                        >
                                            Yes
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Step 3: Location Lock */}
                        {step === 3 && (
                            <div className="space-y-6">
                                <div className="border-b border-[#333] pb-4">
                                    <h1 className="text-[18px] font-semibold text-[#e5e5e5] mb-1">Location Lock</h1>
                                    <p className="text-[11px] text-[#666] font-mono">Confirm launch coordinates</p>
                                </div>

                                {locationError ? (
                                    <div className="bg-[#141414] border border-[#c44] px-3 py-2">
                                        <p className="text-[11px] text-[#c44] font-mono">{locationError}</p>
                                    </div>
                                ) : location ? (
                                    <div className="space-y-4">
                                        <div className="bg-[#141414] border border-[#333] p-3">
                                            <div className="text-[10px] font-semibold text-[#666] uppercase tracking-wider mb-1">Launch Location</div>
                                            <div className="text-[14px] font-semibold text-[#e5e5e5] font-mono mb-1">{locationName}</div>
                                            <div className="text-[10px] text-[#666] font-mono">
                                                {location.lat.toFixed(6)}, {location.lon.toFixed(6)}
                                            </div>
                                        </div>

                                        {/* Mini Map */}
                                        <div className="h-48 border border-[#333] overflow-hidden">
                                            <Map
                                                mapboxAccessToken={process.env.NEXT_PUBLIC_MAPBOX_TOKEN}
                                                initialViewState={{
                                                    longitude: location.lon,
                                                    latitude: location.lat,
                                                    zoom: 14,
                                                }}
                                                style={{ width: '100%', height: '100%' }}
                                                mapStyle="mapbox://styles/mapbox/dark-v11"
                                            >
                                                <Marker
                                                    longitude={location.lon}
                                                    latitude={location.lat}
                                                    anchor="center"
                                                >
                                                    <div className="w-4 h-4 bg-[#4a90d9] rounded-full border border-[#e5e5e5]" />
                                                </Marker>
                                            </Map>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="text-center py-8">
                                        <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-[#4a90d9] border-t-transparent mb-3" />
                                        <p className="text-[11px] text-[#666] font-mono">Acquiring location...</p>
                                    </div>
                                )}

                                <div className="flex gap-3">
                                    <button
                                        onClick={prevStep}
                                        className="flex-1 bg-[#141414] border border-[#333] hover:border-[#666] py-3 text-[12px] font-mono font-semibold text-[#999] hover:text-[#e5e5e5] transition-colors min-h-[44px]"
                                    >
                                        Back
                                    </button>
                                    <button
                                        onClick={nextStep}
                                        disabled={!canProceedFromStep3}
                                        className="flex-1 bg-[#4a90d9] hover:bg-[#4a90d9]/90 disabled:bg-[#333] disabled:text-[#666] disabled:cursor-not-allowed border border-[#4a90d9] disabled:border-[#333] py-3 text-[12px] font-mono font-semibold transition-colors min-h-[44px]"
                                    >
                                        Confirm
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Step 4: The Launch */}
                        {step === 4 && (
                            <div className="space-y-6">
                                <div className="border-b border-[#333] pb-4">
                                    <h1 className="text-[18px] font-semibold text-[#e5e5e5] mb-1">Launch Confirmation</h1>
                                    <p className="text-[11px] text-[#666] font-mono">Hold button to confirm launch</p>
                                </div>

                                <div className="flex flex-col items-center space-y-6">
                                    {/* Hold-to-Launch Button */}
                                    <div className="relative">
                                        {/* Progress Ring */}
                                        <svg className="w-56 h-56 transform -rotate-90" viewBox="0 0 100 100">
                                            <circle
                                                cx="50"
                                                cy="50"
                                                r="45"
                                                fill="none"
                                                stroke="rgba(204, 68, 68, 0.2)"
                                                strokeWidth="3"
                                            />
                                            <motion.circle
                                                cx="50"
                                                cy="50"
                                                r="45"
                                                fill="none"
                                                stroke="#c44"
                                                strokeWidth="3"
                                                strokeLinecap="round"
                                                strokeDasharray={`${2 * Math.PI * 45}`}
                                                initial={{ strokeDashoffset: 2 * Math.PI * 45 }}
                                                animate={{
                                                    strokeDashoffset: 2 * Math.PI * 45 * (1 - holdProgress / 100),
                                                }}
                                                transition={{ duration: 0.1 }}
                                            />
                                        </svg>

                                        {/* Launch Button */}
                                        <button
                                            onMouseDown={handleMouseDown}
                                            onMouseUp={handleMouseUp}
                                            onMouseLeave={handleMouseUp}
                                            onTouchStart={handleMouseDown}
                                            onTouchEnd={handleMouseUp}
                                            disabled={isActivating}
                                            className="absolute inset-0 m-auto w-40 h-40 bg-[#c44] hover:bg-[#c44]/90 disabled:bg-[#333] rounded-full flex items-center justify-center text-[#e5e5e5] font-mono text-[11px] font-semibold border border-[#c44] disabled:border-[#333] transition-all active:scale-95 min-h-[160px] min-w-[160px]"
                                        >
                                            {isActivating ? (
                                                <div className="flex flex-col items-center">
                                                    <div className="animate-spin rounded-full h-6 w-6 border-2 border-[#e5e5e5] border-t-transparent mb-2" />
                                                    <span className="text-[10px]">Launching...</span>
                                                </div>
                                            ) : (
                                                <span className="text-center px-2">HOLD TO<br />LAUNCH</span>
                                            )}
                                        </button>
                                    </div>

                                    <div className="text-center space-y-2">
                                        <p className="text-[11px] font-mono text-[#666]">
                                            {isHolding ? 'Keep holding...' : 'Hold for 3 seconds'}
                                        </p>
                                        {isHolding && (
                                            <p className="text-[18px] font-bold text-[#c44] font-mono">
                                                {Math.ceil((100 - holdProgress) / (100 / 3))}s
                                            </p>
                                        )}
                                    </div>

                                    <button
                                        onClick={prevStep}
                                        className="w-full bg-[#141414] border border-[#333] hover:border-[#666] py-3 text-[12px] font-mono font-semibold text-[#999] hover:text-[#e5e5e5] transition-colors min-h-[44px]"
                                    >
                                        Back
                                    </button>
                                </div>
                            </div>
                        )}
                    </motion.div>
                </AnimatePresence>
            </div>
        </div>
    );
}
