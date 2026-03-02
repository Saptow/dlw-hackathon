import { useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Html } from '@react-three/drei';
import * as THREE from 'three';
import type { TelemetryData } from '../types';

interface StationModelProps {
    devices: TelemetryData[];
    globalThreshold: number;
}

// Map logical locations to 3D spatial coordinates [x, y, z]
const LOCATION_COORDINATES: Record<string, [number, number, number]> = {
    "Platform 1 (West)": [-3, 0.8, 0],
    "Platform 2 (East)": [3, 0.8, 0],
    "Concourse": [0, 0.01, 5],
    "Turnstiles": [0, 0.01, 2]
};

function HeatCircle({ device, globalThreshold }: { device: TelemetryData, globalThreshold: number }) {
    const meshRef = useRef<THREE.Mesh>(null);
    const { metrics, status, location_label } = device;

    const position = LOCATION_COORDINATES[location_label] || [0, 0.01, 0];
    const isCritical = metrics.threshold >= globalThreshold;

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
            {/* Base Floor (Concourse level) */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow position={[0, -0.25, 4]}>
                <boxGeometry args={[16, 6, 0.5]} />
                <meshStandardMaterial color="#334155" roughness={0.9} />
            </mesh>

            {/* Platform 1 (West Raised) */}
            <mesh position={[-3, 0.25, -2]} receiveShadow castShadow>
                <boxGeometry args={[4, 1, 12]} />
                <meshStandardMaterial color="#475569" roughness={0.8} />
            </mesh>

            {/* Platform 2 (East Raised) */}
            <mesh position={[3, 0.25, -2]} receiveShadow castShadow>
                <boxGeometry args={[4, 1, 12]} />
                <meshStandardMaterial color="#475569" roughness={0.8} />
            </mesh>

            {/* Train Tracks (Recessed Pit between platforms) */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.4, -2]} receiveShadow>
                <boxGeometry args={[2, 12, 0.1]} />
                <meshStandardMaterial color="#0f172a" roughness={1} />
            </mesh>

            {/* Track Rails */}
            <mesh position={[-0.5, -0.35, -2]} castShadow receiveShadow>
                <boxGeometry args={[0.05, 0.1, 12]} />
                <meshStandardMaterial color="#64748b" metalness={0.8} roughness={0.2} />
            </mesh>
            <mesh position={[0.5, -0.35, -2]} castShadow receiveShadow>
                <boxGeometry args={[0.05, 0.1, 12]} />
                <meshStandardMaterial color="#64748b" metalness={0.8} roughness={0.2} />
            </mesh>

            {/* Turnstiles / Gates */}
            {[-1.5, -0.5, 0.5, 1.5].map((x, i) => (
                <group key={i} position={[x, 0.5, 2]}>
                    <mesh castShadow position={[0, 0, 0]}>
                        <boxGeometry args={[0.2, 1, 0.8]} />
                        <meshStandardMaterial color="#1e293b" />
                    </mesh>
                    <mesh position={[0.2, 0.2, 0.3]} rotation={[0, 0, -0.3]}>
                        <boxGeometry args={[0.4, 0.05, 0.05]} />
                        <meshStandardMaterial color="#ef4444" />
                    </mesh>
                </group>
            ))}

            {/* Overhead Info Boards */}
            <mesh position={[-3, 3, -2]} castShadow>
                <boxGeometry args={[2, 0.5, 0.1]} />
                <meshStandardMaterial color="#020617" />
            </mesh>
            <mesh position={[3, 3, -2]} castShadow>
                <boxGeometry args={[2, 0.5, 0.1]} />
                <meshStandardMaterial color="#020617" />
            </mesh>

            <mesh position={[-3, 4, -2]} castShadow>
                <boxGeometry args={[0.1, 2, 0.1]} />
                <meshStandardMaterial color="#334155" />
            </mesh>
            <mesh position={[3, 4, -2]} castShadow>
                <boxGeometry args={[0.1, 2, 0.1]} />
                <meshStandardMaterial color="#334155" />
            </mesh>

            {/* Lighting - Increased intensity so the dark floor/pillars are visible */}
            <ambientLight intensity={1.5} />
            <directionalLight position={[10, 15, 10]} intensity={2.5} castShadow />
            <pointLight position={[0, 8, 0]} intensity={2} color="#acc8f2" />
        </group>
    );
}

export function StationModel({ devices, globalThreshold }: StationModelProps) {
    return (
        <div className="glass-panel overflow-hidden relative border-white/10 w-full h-[400px] md:h-full min-h-[400px]">
            <div className="absolute top-4 left-4 z-10 pointer-events-none">
                <h3 className="font-semibold text-lg text-slate-100 tracking-wide drop-shadow-md">Digital Twin View</h3>
                <p className="text-xs text-slate-400 font-mono uppercase tracking-widest drop-shadow-md">Live Platform Heatmap</p>
            </div>

            <Canvas shadows camera={{ position: [8, 8, 8], fov: 45 }}>
                <color attach="background" args={['#020617']} />

                <StationEnvironment />

                {devices.map(device => (
                    <HeatCircle key={device.device_id} device={device} globalThreshold={globalThreshold} />
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
