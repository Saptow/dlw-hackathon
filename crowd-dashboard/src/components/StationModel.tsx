import { useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Html } from '@react-three/drei';
import * as THREE from 'three';
import type { TelemetryData } from '../types';

interface StationModelProps {
    devices: TelemetryData[];
}

// Map logical locations to 3D spatial coordinates [x, y, z]
const LOCATION_COORDINATES: Record<string, [number, number, number]> = {
    "North Gate Area": [0, 0.01, -4],
    "Central Plaza": [0, 0.01, 0],
    "Subway Entrance A": [4, 0.01, 0],
    "South Checkpoint": [0, 0.01, 4]
};

function HeatCircle({ device }: { device: TelemetryData }) {
    const meshRef = useRef<THREE.Mesh>(null);
    const { metrics, status, location_label } = device;

    const position = LOCATION_COORDINATES[location_label] || [0, 0.01, 0];
    const isCritical = metrics.threshold >= 0.8;

    // Determine color
    let color = "#10b981"; // emerald-500 (safe)
    if (isCritical) {
        color = "#ef4444"; // red-500 (critical)
    } else if (metrics.threshold >= 0.4) {
        color = "#f59e0b"; // amber-500 (warning)
    }

    const isReliable = status === "active";

    // Pulsing animation based on density
    useFrame(({ clock }) => {
        if (meshRef.current && isReliable) {
            // Pulse speed and magnitude scale with the risk threshold
            const baseScale = 1 + (metrics.threshold * 0.5);
            const pulse = Math.sin(clock.getElapsedTime() * (2 + metrics.threshold * 5)) * 0.1;
            const scale = baseScale + pulse;
            meshRef.current.scale.set(scale, scale, 1);
        }
    });

    return (
        <group position={position}>
            {/* The Heatmap Circle */}
            <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]}>
                <circleGeometry args={[1, 32]} />
                <meshBasicMaterial
                    color={color}
                    transparent
                    opacity={isReliable ? 0.6 : 0.2}
                    depthWrite={false}
                />
            </mesh>

            {/* HTML Data Overlay */}
            <Html position={[0, 1, 0]} center zIndexRange={[100, 0]}>
                <div className={`pointer-events-none whitespace-nowrap px-3 py-1.5 rounded-lg border backdrop-blur-md shadow-xl transition-all ${!isReliable ? 'bg-slate-900/60 border-slate-700 grayscale' :
                    isCritical ? 'bg-red-950/80 border-red-500/50 shadow-[0_0_15px_rgba(239,68,68,0.5)]' :
                        'bg-slate-900/80 border-white/10'
                    }`}>
                    <div className="text-[10px] font-mono text-slate-400 uppercase tracking-wider mb-0.5">
                        {location_label}
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="flex flex-col">
                            <span className="text-white font-bold text-sm leading-none">{metrics.people_count}</span>
                            <span className="text-[8px] text-slate-500 uppercase">PPL</span>
                        </div>
                        <div className="flex flex-col">
                            <span className={`font-bold font-mono text-sm leading-none ${isCritical ? 'text-red-400' : 'text-emerald-400'}`}>
                                {metrics.crowd_density.toFixed(2)}
                            </span>
                            <span className="text-[8px] text-slate-500 uppercase">PPL/m²</span>
                        </div>
                    </div>
                </div>
            </Html>
        </group>
    );
}

function StationEnvironment() {
    return (
        <group>
            {/* Main Platform Floor */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow position={[0, -0.25, 0]}>
                <boxGeometry args={[15, 15, 0.5]} />
                <meshStandardMaterial color="#334155" roughness={0.9} />
            </mesh>

            {/* Central Pillar */}
            <mesh position={[0, 1.5, 0]} castShadow>
                <boxGeometry args={[1.5, 3, 1.5]} />
                <meshStandardMaterial color="#475569" roughness={0.7} />
            </mesh>

            {/* Corner Pillars */}
            <mesh position={[-6, 1.5, -6]} castShadow>
                <boxGeometry args={[0.8, 3, 0.8]} />
                <meshStandardMaterial color="#475569" roughness={0.7} />
            </mesh>
            <mesh position={[6, 1.5, -6]} castShadow>
                <boxGeometry args={[0.8, 3, 0.8]} />
                <meshStandardMaterial color="#475569" roughness={0.7} />
            </mesh>
            <mesh position={[-6, 1.5, 6]} castShadow>
                <boxGeometry args={[0.8, 3, 0.8]} />
                <meshStandardMaterial color="#475569" roughness={0.7} />
            </mesh>
            <mesh position={[6, 1.5, 6]} castShadow>
                <boxGeometry args={[0.8, 3, 0.8]} />
                <meshStandardMaterial color="#475569" roughness={0.7} />
            </mesh>

            {/* Lighting - Increased intensity so the dark floor/pillars are visible */}
            <ambientLight intensity={1.5} />
            <directionalLight position={[10, 15, 10]} intensity={2.5} castShadow />
            <pointLight position={[0, 8, 0]} intensity={2} color="#acc8f2" />
        </group>
    );
}

export function StationModel({ devices }: StationModelProps) {
    return (
        <div className="glass-panel overflow-hidden relative border-white/10 w-full h-[400px] md:h-full min-h-[400px]">
            <div className="absolute top-4 left-4 z-10 pointer-events-none">
                <h3 className="font-semibold text-lg text-slate-100 tracking-wide drop-shadow-md">Digital Twin View</h3>
                <p className="text-xs text-slate-400 font-mono uppercase tracking-widest drop-shadow-md">Live Platform Heatmap</p>
            </div>

            <Canvas shadows camera={{ position: [8, 8, 8], fov: 45 }}>
                <color attach="background" args={['#020617']} />
                <fog attach="fog" args={['#020617', 10, 30]} />

                <StationEnvironment />

                {devices.map(device => (
                    <HeatCircle key={device.device_id} device={device} />
                ))}

                <OrbitControls
                    enableDamping
                    maxPolarAngle={Math.PI / 2.2} // Prevent looking directly from below
                    minDistance={5}
                    maxDistance={25}
                />
            </Canvas>
        </div>
    );
}
