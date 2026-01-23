'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

/**
 * QR Code Scanner Component
 * 
 * Uses the device camera to scan QR codes and navigate to activation page
 * 
 * Note: Requires HTTPS or localhost for camera access
 */
export default function QRCodeScanner({ onScan }: { onScan?: (deviceId: string) => void }) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [isScanning, setIsScanning] = useState(false);
    const [error, setError] = useState<string>('');
    const router = useRouter();

    useEffect(() => {
        let stream: MediaStream | null = null;
        let animationFrameId: number;

        const startScanning = async () => {
            try {
                // Request camera access
                stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'environment' } // Use back camera on mobile
                });

                if (videoRef.current) {
                    videoRef.current.srcObject = stream;
                    setIsScanning(true);
                    setError('');
                }

                // Start QR code detection
                // Note: For production, use a library like @zxing/library or html5-qrcode
                // This is a placeholder - you'll need to integrate a QR scanner library
                const scanFrame = () => {
                    if (videoRef.current && canvasRef.current) {
                        const video = videoRef.current;
                        const canvas = canvasRef.current;
                        const context = canvas.getContext('2d');

                        if (context && video.readyState === video.HAVE_ENOUGH_DATA) {
                            canvas.width = video.videoWidth;
                            canvas.height = video.videoHeight;
                            context.drawImage(video, 0, 0, canvas.width, canvas.height);

                            // TODO: Add QR code detection here
                            // Example with html5-qrcode:
                            // const codeReader = new BrowserQRCodeReader();
                            // codeReader.decodeFromVideoDevice(null, video.id, (result) => {
                            //     if (result) {
                            //         handleQRCode(result.getText());
                            //     }
                            // });
                        }
                    }
                    animationFrameId = requestAnimationFrame(scanFrame);
                };

                scanFrame();
            } catch (err) {
                console.error('Error accessing camera:', err);
                setError('Unable to access camera. Please ensure you have granted camera permissions.');
            }
        };

        startScanning();

        return () => {
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
            }
            if (animationFrameId) {
                cancelAnimationFrame(animationFrameId);
            }
        };
    }, []);

    const handleQRCode = (text: string) => {
        // Extract device ID from URL or direct device ID
        // URL format: https://stratolink.org/activate/balloon-001
        const match = text.match(/activate\/([^\/\?]+)/);
        const deviceId = match ? match[1] : text;

        if (deviceId) {
            if (onScan) {
                onScan(deviceId);
            } else {
                router.push(`/activate/${deviceId}`);
            }
        }
    };

    if (error) {
        return (
            <div className="bg-[#141414] border border-[#333] p-4 rounded text-center">
                <p className="text-[#c44] text-[12px] mb-2">{error}</p>
                <p className="text-[#666] text-[10px]">
                    You can also manually enter the device ID or scan the QR code with your phone's camera app.
                </p>
            </div>
        );
    }

    return (
        <div className="relative">
            <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-64 bg-black rounded border border-[#333]"
            />
            <canvas ref={canvasRef} className="hidden" />
            {isScanning && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="border-2 border-[#4a90d9] rounded-lg w-48 h-48" />
                </div>
            )}
        </div>
    );
}
