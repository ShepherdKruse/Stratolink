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
            // Redirect to dashboard with ride along mode
            router.push(`/dashboard?mode=ride_along&balloon=${deviceId}`);
        } else {
            alert(result.error || 'Launch failed');
            setIsActivating(false);
            setIsHolding(false);
            setHoldProgress(0);
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
        <div className="min-h-screen bg-slate-900 text-white">
            {/* Progress Indicator */}
            <div className="fixed top-0 left-0 right-0 h-1 bg-slate-800 z-50">
                <div
                    className="h-full bg-green-500 transition-all duration-300"
                    style={{ width: `${(step / 4) * 100}%` }}
                />
            </div>

            {/* Step Counter */}
            <div className="fixed top-4 right-4 z-40">
                <div className="bg-slate-800/90 backdrop-blur-sm px-4 py-2 rounded border border-slate-700">
                    <span className="text-sm font-mono text-green-400">
                        Step {step} of 4
                    </span>
                </div>
            </div>

            <div className="container mx-auto px-4 py-16 pt-24">
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
                            <div className="space-y-8">
                                <div>
                                    <h1 className="text-3xl font-bold mb-2 text-green-400">Device Activation</h1>
                                    <p className="text-slate-400">Enter your activation credentials</p>
                                </div>

                                <div className="space-y-6">
                                    <div>
                                        <label className="block text-sm font-semibold mb-2 text-slate-300">
                                            Device ID
                                        </label>
                                        <div className="bg-slate-800 border border-slate-700 px-4 py-3 rounded font-mono text-lg">
                                            {deviceId || 'Loading...'}
                                        </div>
                                    </div>

                                    <div>
                                        <label className="block text-sm font-semibold mb-2 text-slate-300">
                                            Activation PIN (6 digits)
                                        </label>
                                        <input
                                            type="text"
                                            inputMode="numeric"
                                            maxLength={6}
                                            value={pin}
                                            onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
                                            className="w-full bg-slate-800 border border-slate-700 px-4 py-4 rounded text-2xl font-mono text-center tracking-widest focus:outline-none focus:border-green-500"
                                            placeholder="000000"
                                        />
                                    </div>

                                    <div>
                                        <label className="block text-sm font-semibold mb-2 text-slate-300">
                                            Mission Commander Name
                                        </label>
                                        <input
                                            type="text"
                                            value={name}
                                            onChange={(e) => setName(e.target.value)}
                                            className="w-full bg-slate-800 border border-slate-700 px-4 py-4 rounded text-lg focus:outline-none focus:border-green-500"
                                            placeholder="Your name"
                                        />
                                    </div>
                                </div>

                                <button
                                    onClick={nextStep}
                                    disabled={!canProceedFromStep1}
                                    className="w-full bg-green-500 hover:bg-green-600 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed py-4 rounded text-lg font-semibold transition-colors"
                                >
                                    Continue
                                </button>
                            </div>
                        )}

                        {/* Step 2: Hardware Verification */}
                        {step === 2 && (
                            <div className="space-y-8">
                                <div>
                                    <h1 className="text-3xl font-bold mb-2 text-green-400">Hardware Check</h1>
                                    <p className="text-slate-400">Verify device is powered on</p>
                                </div>

                                <div className="flex flex-col items-center space-y-6">
                                    {/* Animated Switch */}
                                    <div className="relative w-32 h-16">
                                        <motion.div
                                            animate={{
                                                scale: [1, 1.1, 1],
                                            }}
                                            transition={{
                                                duration: 1.5,
                                                repeat: Infinity,
                                                ease: 'easeInOut',
                                            }}
                                            className="absolute inset-0 bg-slate-800 rounded-full border-4 border-slate-700"
                                        />
                                        <motion.div
                                            animate={{
                                                x: [0, 64, 0],
                                            }}
                                            transition={{
                                                duration: 1.5,
                                                repeat: Infinity,
                                                ease: 'easeInOut',
                                            }}
                                            className="absolute top-1 left-1 w-14 h-14 bg-green-500 rounded-full shadow-lg shadow-green-500/50"
                                        />
                                    </div>

                                    <div className="text-center space-y-4">
                                        <p className="text-xl font-semibold">Power Switch ON</p>
                                        <p className="text-slate-400">Do you see the Green LED flashing?</p>
                                    </div>

                                    <div className="flex gap-4 w-full">
                                        <button
                                            onClick={() => {
                                                setLedConfirmed(false);
                                                prevStep();
                                            }}
                                            className="flex-1 bg-slate-800 border border-slate-700 hover:border-slate-600 py-4 rounded text-lg font-semibold transition-colors"
                                        >
                                            No
                                        </button>
                                        <button
                                            onClick={() => {
                                                setLedConfirmed(true);
                                                nextStep();
                                            }}
                                            className="flex-1 bg-green-500 hover:bg-green-600 py-4 rounded text-lg font-semibold transition-colors"
                                        >
                                            Yes
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Step 3: Location Lock */}
                        {step === 3 && (
                            <div className="space-y-8">
                                <div>
                                    <h1 className="text-3xl font-bold mb-2 text-green-400">Location Lock</h1>
                                    <p className="text-slate-400">Confirm launch coordinates</p>
                                </div>

                                {locationError ? (
                                    <div className="bg-red-900/30 border border-red-700 px-4 py-3 rounded text-red-400">
                                        {locationError}
                                    </div>
                                ) : location ? (
                                    <div className="space-y-4">
                                        <div className="bg-slate-800 border border-slate-700 rounded p-4">
                                            <div className="text-sm text-slate-400 mb-1">Launch Location</div>
                                            <div className="text-xl font-semibold">{locationName}</div>
                                            <div className="text-sm text-slate-500 font-mono mt-1">
                                                {location.lat.toFixed(6)}, {location.lon.toFixed(6)}
                                            </div>
                                        </div>

                                        {/* Mini Map */}
                                        <div className="h-64 rounded border border-slate-700 overflow-hidden">
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
                                                    <div className="w-6 h-6 bg-red-500 rounded-full border-2 border-white shadow-lg animate-pulse" />
                                                </Marker>
                                            </Map>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="text-center py-8">
                                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-green-500 border-t-transparent mb-4" />
                                        <p className="text-slate-400">Acquiring location...</p>
                                    </div>
                                )}

                                <div className="flex gap-4">
                                    <button
                                        onClick={prevStep}
                                        className="flex-1 bg-slate-800 border border-slate-700 hover:border-slate-600 py-4 rounded text-lg font-semibold transition-colors"
                                    >
                                        Back
                                    </button>
                                    <button
                                        onClick={nextStep}
                                        disabled={!canProceedFromStep3}
                                        className="flex-1 bg-green-500 hover:bg-green-600 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed py-4 rounded text-lg font-semibold transition-colors"
                                    >
                                        Confirm Location
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Step 4: The Launch */}
                        {step === 4 && (
                            <div className="space-y-8">
                                <div>
                                    <h1 className="text-3xl font-bold mb-2 text-red-400">Launch Confirmation</h1>
                                    <p className="text-slate-400">Hold the button to launch</p>
                                </div>

                                <div className="flex flex-col items-center space-y-6">
                                    {/* Hold-to-Launch Button */}
                                    <div className="relative">
                                        {/* Progress Ring */}
                                        <svg className="w-64 h-64 transform -rotate-90" viewBox="0 0 100 100">
                                            <circle
                                                cx="50"
                                                cy="50"
                                                r="45"
                                                fill="none"
                                                stroke="rgba(239, 68, 68, 0.2)"
                                                strokeWidth="4"
                                            />
                                            <motion.circle
                                                cx="50"
                                                cy="50"
                                                r="45"
                                                fill="none"
                                                stroke="#ef4444"
                                                strokeWidth="4"
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
                                            className="absolute inset-0 m-auto w-48 h-48 bg-red-600 hover:bg-red-700 disabled:bg-slate-700 rounded-full flex items-center justify-center text-white font-bold text-xl shadow-2xl shadow-red-600/50 transition-all active:scale-95"
                                        >
                                            {isActivating ? (
                                                <div className="flex flex-col items-center">
                                                    <div className="animate-spin rounded-full h-8 w-8 border-4 border-white border-t-transparent mb-2" />
                                                    <span>Launching...</span>
                                                </div>
                                            ) : (
                                                'HOLD TO LAUNCH'
                                            )}
                                        </button>
                                    </div>

                                    <div className="text-center space-y-2">
                                        <p className="text-lg font-semibold">
                                            {isHolding ? 'Keep holding...' : 'Hold for 3 seconds'}
                                        </p>
                                        {isHolding && (
                                            <p className="text-2xl font-bold text-red-400">
                                                {Math.ceil((100 - holdProgress) / (100 / 3))}s
                                            </p>
                                        )}
                                    </div>

                                    <button
                                        onClick={prevStep}
                                        className="w-full bg-slate-800 border border-slate-700 hover:border-slate-600 py-4 rounded text-lg font-semibold transition-colors"
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
