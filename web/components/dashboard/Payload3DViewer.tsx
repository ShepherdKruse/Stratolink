'use client';

import { useRef, Suspense, useState, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, useGLTF } from '@react-three/drei';
import * as THREE from 'three';

// Preload the model for better performance
useGLTF.preload('/models/payload_v1.glb');

// Load external PCB model if available
function ExternalPCBModel({ modelPath }: { modelPath: string }) {
    const { scene } = useGLTF(modelPath);
    const groupRef = useRef<THREE.Group>(null);
    
    // Auto-rotation (around Y axis for vertical orientation)
    useFrame((state, delta) => {
        if (groupRef.current) {
            groupRef.current.rotation.y += delta * 0.2;
        }
    });
    
    // Calculate bounding box to center, scale, and orient the model vertically
    useEffect(() => {
        if (scene && groupRef.current) {
            const box = new THREE.Box3().setFromObject(scene);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            const scale = 3 / maxDim; // Scale to fit in ~3 unit space
            
            scene.position.sub(center); // Center the model
            groupRef.current.scale.set(scale, scale, scale);
            
            // Enhance materials for better visibility
            scene.traverse((child) => {
                if (child instanceof THREE.Mesh) {
                    if (child.material instanceof THREE.MeshStandardMaterial) {
                        // Increase contrast and reduce washout
                        child.material.metalness = Math.min(0.8, (child.material.metalness || 0) + 0.2);
                        child.material.roughness = Math.max(0.3, (child.material.roughness || 0.5) - 0.2);
                        // Add slight emissive for visibility
                        if (!child.material.emissive) {
                            child.material.emissive = new THREE.Color(0x000000);
                        }
                        child.material.emissiveIntensity = 0.1;
                    } else if (Array.isArray(child.material)) {
                        // Handle material arrays
                        child.material.forEach((mat: any) => {
                            if (mat instanceof THREE.MeshStandardMaterial) {
                                mat.metalness = Math.min(0.8, (mat.metalness || 0) + 0.2);
                                mat.roughness = Math.max(0.3, (mat.roughness || 0.5) - 0.2);
                                if (!mat.emissive) {
                                    mat.emissive = new THREE.Color(0x000000);
                                }
                                mat.emissiveIntensity = 0.1;
                                mat.needsUpdate = true;
                            }
                        });
                    }
                    // Make sure materials are updated
                    if (child.material && !Array.isArray(child.material)) {
                        child.material.needsUpdate = true;
                    }
                }
            });
        }
    }, [scene]);
    
    return (
        <group ref={groupRef} position={[0, 0, 0]}>
            <primitive object={scene} />
        </group>
    );
}

// Simple PCB-like geometry component (fallback)
function SimplePCBModel() {
    const groupRef = useRef<THREE.Group>(null);
    
    // Auto-rotation
    useFrame((state, delta) => {
        if (groupRef.current) {
            groupRef.current.rotation.y += delta * 0.2; // Slow rotation
        }
    });

    return (
        <group ref={groupRef}>
            {/* Main PCB Board - Much brighter green */}
            <mesh position={[0, 0, 0]}>
                <boxGeometry args={[3, 2, 0.1]} />
                <meshStandardMaterial 
                    color="#2d7a4d" 
                    metalness={0.2} 
                    roughness={0.6}
                    emissive="#1a5a3a"
                    emissiveIntensity={0.3}
                />
            </mesh>

            {/* PCB Traces (visible lines) */}
            <mesh position={[0, 0, 0.05]}>
                <boxGeometry args={[2.8, 0.05, 0.02]} />
                <meshStandardMaterial color="#4a9a6a" emissive="#2a7a4a" emissiveIntensity={0.4} />
            </mesh>
            <mesh position={[0, 0, 0.05]}>
                <boxGeometry args={[0.05, 1.8, 0.02]} />
                <meshStandardMaterial color="#4a9a6a" emissive="#2a7a4a" emissiveIntensity={0.4} />
            </mesh>

            {/* Components on PCB - Brighter and more visible */}
            {/* Microcontroller */}
            <mesh position={[-0.8, 0.5, 0.06]}>
                <boxGeometry args={[0.4, 0.4, 0.12]} />
                <meshStandardMaterial 
                    color="#3d704d" 
                    metalness={0.4} 
                    roughness={0.5}
                    emissive="#2d604d"
                    emissiveIntensity={0.2}
                />
            </mesh>

            {/* LoRa Module */}
            <mesh position={[0.8, 0.5, 0.06]}>
                <boxGeometry args={[0.3, 0.5, 0.12]} />
                <meshStandardMaterial 
                    color="#2d604d" 
                    metalness={0.5} 
                    roughness={0.4}
                    emissive="#1d504d"
                    emissiveIntensity={0.25}
                />
            </mesh>

            {/* GPS Module */}
            <mesh position={[-0.8, -0.5, 0.06]}>
                <boxGeometry args={[0.4, 0.3, 0.12]} />
                <meshStandardMaterial 
                    color="#3d704d" 
                    metalness={0.4} 
                    roughness={0.5}
                    emissive="#2d604d"
                    emissiveIntensity={0.2}
                />
            </mesh>

            {/* Power Management IC */}
            <mesh position={[0.8, -0.5, 0.06]}>
                <boxGeometry args={[0.3, 0.3, 0.12]} />
                <meshStandardMaterial 
                    color="#2d604d" 
                    metalness={0.5} 
                    roughness={0.4}
                    emissive="#1d504d"
                    emissiveIntensity={0.25}
                />
            </mesh>

            {/* Connectors - More visible */}
            <mesh position={[-1.3, 0, 0.06]}>
                <boxGeometry args={[0.1, 0.6, 0.12]} />
                <meshStandardMaterial 
                    color="#6a6a6a" 
                    metalness={0.7} 
                    roughness={0.2}
                    emissive="#4a4a4a"
                    emissiveIntensity={0.15}
                />
            </mesh>

            {/* LED Indicators - Brighter */}
            <mesh position={[1.2, 0.3, 0.06]}>
                <cylinderGeometry args={[0.05, 0.05, 0.12, 16]} />
                <meshStandardMaterial 
                    color="#00ff00" 
                    emissive="#00ff00" 
                    emissiveIntensity={1.5}
                />
            </mesh>
            
            {/* Additional LED for visibility */}
            <mesh position={[-1.2, 0.3, 0.06]}>
                <cylinderGeometry args={[0.04, 0.04, 0.12, 16]} />
                <meshStandardMaterial 
                    color="#00ffff" 
                    emissive="#00ffff" 
                    emissiveIntensity={1.2}
                />
            </mesh>
        </group>
    );
}

export default function Payload3DViewer() {
    // Try to load external model, fallback to simple model if not found
    const modelPath = '/models/payload_v1.glb';
    const [useExternalModel, setUseExternalModel] = useState(false);
    
    useEffect(() => {
        // Check if model file exists
        fetch(modelPath, { method: 'HEAD' })
            .then(res => {
                if (res.ok) {
                    setUseExternalModel(true);
                }
            })
            .catch(() => {
                // Model not found, use simple model
                setUseExternalModel(false);
            });
    }, [modelPath]);
    
    return (
        <div className="w-full h-full bg-gradient-to-br from-gray-900 to-black">
            <Canvas>
                <PerspectiveCamera makeDefault position={[3, 3, 3]} fov={50} />
                
                {/* Enhanced lighting for better visibility and contrast - reduced washout */}
                <ambientLight intensity={0.8} />
                <directionalLight position={[5, 10, 5]} intensity={2.5} castShadow />
                <directionalLight position={[-5, 10, -5]} intensity={1.8} />
                <directionalLight position={[0, -5, 0]} intensity={0.5} />
                <pointLight position={[3, 3, 3]} intensity={1.2} />
                <pointLight position={[-3, 3, -3]} intensity={0.8} />
                <spotLight position={[0, 8, 0]} angle={0.5} intensity={1.5} penumbra={0.5} />
                
                <Suspense fallback={
                    <mesh>
                        <boxGeometry args={[1, 1, 1]} />
                        <meshStandardMaterial color="#00ffff" wireframe />
                    </mesh>
                }>
                    {useExternalModel ? (
                        <ExternalPCBModel modelPath={modelPath} />
                    ) : (
                        <SimplePCBModel />
                    )}
                </Suspense>
                
                <OrbitControls
                    enablePan={true}
                    enableZoom={true}
                    enableRotate={true}
                    minDistance={2}
                    maxDistance={15}
                    target={[0, 0, 0]}
                />
            </Canvas>
        </div>
    );
}
