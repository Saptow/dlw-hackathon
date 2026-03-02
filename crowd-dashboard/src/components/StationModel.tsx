import React, { useRef, useMemo } from 'react';
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
    "Platform 1 (West)": [-3, 0.8, -3.5],
    "Platform 2 (East)": [3, 0.8, -3.5],
    "Concourse": [0, 0.01, 5],
    "Turnstiles": [0, 0.01, 2]
};

export type PatrolArea = "Platform 1 (West)" | "Platform 2 (East)" | "Concourse" | "Turnstiles";

export const PATROL_ZONES: Record<PatrolArea, { minX: number, maxX: number, minZ: number, maxZ: number, yPos: number }> = {
    "Platform 1 (West)": { minX: -4.5, maxX: -1.5, minZ: -7, maxZ: 3, yPos: 0.83 },
    "Platform 2 (East)": { minX: 1.5, maxX: 4.5, minZ: -7, maxZ: 3, yPos: 0.83 },
    "Concourse": { minX: -6, maxX: 6, minZ: 2, maxZ: 6, yPos: 0.08 },
    "Turnstiles": { minX: -1.5, maxX: 1.5, minZ: 1.5, maxZ: 2.5, yPos: 0.08 },
};

const HeatCircle = React.memo(function HeatCircle({ device, globalThreshold }: { device: TelemetryData, globalThreshold: number }) {
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
});

const PersonDot = React.memo(function PersonDot({ initialArea }: { initialArea: PatrolArea }) {
    const meshRef = useRef<THREE.Mesh>(null);
    const [area, setArea] = React.useState<PatrolArea>(initialArea);
    const [showMenu, setShowMenu] = React.useState(false);
    const [isRelocating, setIsRelocating] = React.useState(false);

    // Instead of a single target, we maintain a queue of waypoints
    const targetsQueue = useRef<THREE.Vector3[]>([]);

    const speed = useMemo(() => 0.3 + Math.random() * 0.2, []); // Walking speed
    const initialized = useRef(false);

    // Watch for zone changes and generate a path to the new target
    React.useEffect(() => {
        const targetZone = PATROL_ZONES[area];
        const finalDest = new THREE.Vector3(
            targetZone.minX + Math.random() * (targetZone.maxX - targetZone.minX),
            targetZone.yPos,
            targetZone.minZ + Math.random() * (targetZone.maxZ - targetZone.minZ)
        );

        if (!initialized.current && meshRef.current) {
            // First spawn: just pop right to the final dest
            meshRef.current.position.copy(finalDest);
            targetsQueue.current = [finalDest];
            initialized.current = true;
            return;
        }

        if (!meshRef.current) return;
        const currentPos = meshRef.current.position;

        // Pathfinding logic: 
        // Platforms are at y=0.83, Concourse/Turnstiles are at y=0.08
        // If we are changing height, we need to route through the "stairs"
        // Let's define the stairs to be at Z = 2 on the inner edge of platforms

        const path: THREE.Vector3[] = [];
        const isCurrentlyRaised = currentPos.y > 0.4;
        const isTargetRaised = targetZone.yPos > 0.4;

        if (isCurrentlyRaised && !isTargetRaised) {
            // Going DOWN to concourse
            // 1. Walk to the edge of current platform (Z=2)
            path.push(new THREE.Vector3(currentPos.x, currentPos.y, 2));
            // 2. Drop down to concourse level
            path.push(new THREE.Vector3(currentPos.x, targetZone.yPos, 2));
            // 3. Finally walk to destination
            path.push(finalDest);
        } else if (!isCurrentlyRaised && isTargetRaised) {
            // Going UP to platform
            // 1. Walk to the concourse edge below target platform (Z=2, target X)
            path.push(new THREE.Vector3(finalDest.x, currentPos.y, 2));
            // 2. Climb up to platform level
            path.push(new THREE.Vector3(finalDest.x, targetZone.yPos, 2));
            // 3. Finally walk to destination
            path.push(finalDest);
        } else if (isCurrentlyRaised && isTargetRaised && Math.abs(currentPos.x - finalDest.x) > 4) {
            // Going from Platform 1 (West) to Platform 2 (East) directly
            // Must go down, cross concourse, and go back up
            path.push(new THREE.Vector3(currentPos.x, currentPos.y, 2)); // Edge of plat 1
            path.push(new THREE.Vector3(currentPos.x, PATROL_ZONES["Concourse"].yPos, 2)); // Down
            path.push(new THREE.Vector3(finalDest.x, PATROL_ZONES["Concourse"].yPos, 2)); // Cross concourse
            path.push(new THREE.Vector3(finalDest.x, targetZone.yPos, 2)); // Up plat 2
            path.push(finalDest); // Final spot
        } else {
            // Same height, no crossing track gap: just walk straight
            path.push(finalDest);
        }

        targetsQueue.current = path;
        setIsRelocating(true);

    }, [area]);

    useFrame((_, delta) => {
        if (!meshRef.current) return;
        if (targetsQueue.current.length === 0) return;

        const pos = meshRef.current.position;
        const currentTarget = targetsQueue.current[0];
        const dist = pos.distanceTo(currentTarget);

        if (dist < 0.2) {
            // Reached current waypoint
            targetsQueue.current.shift();

            if (targetsQueue.current.length === 0) {
                // Reached final destination
                if (isRelocating) setIsRelocating(false);

                // Keep wandering in current zone
                const zone = PATROL_ZONES[area];
                targetsQueue.current.push(new THREE.Vector3(
                    zone.minX + Math.random() * (zone.maxX - zone.minX),
                    zone.yPos,
                    zone.minZ + Math.random() * (zone.maxZ - zone.minZ)
                ));
            }
        } else {
            // Move towards target smoothly. Move faster if relocating.
            const dir = currentTarget.clone().sub(pos).normalize();
            const currentSpeed = isRelocating ? speed * 2.0 : speed;
            pos.add(dir.multiplyScalar(currentSpeed * delta));
        }
    });

    return (
        <group>
            <mesh
                ref={meshRef}
                castShadow
                onClick={(e) => { e.stopPropagation(); setShowMenu(true); }}
                onPointerMissed={(e) => { if (e.type === 'click') setShowMenu(false); }}
            >
                <sphereGeometry args={[0.15, 16, 16]} />
                <meshStandardMaterial color={showMenu ? "#38bdf8" : isRelocating ? "#f59e0b" : "#94a3b8"} roughness={0.4} />

                {/* Always show a small indicator above their head, but expand when menu is open */}
                <Html position={[0, 0.3, 0]} center zIndexRange={[100, 0]} className="pointer-events-none">
                    {!showMenu && (
                        <div className={`text-white text-[8px] px-1 rounded font-mono shadow border whitespace-nowrap transition-colors ${isRelocating ? 'bg-amber-600/80 border-amber-400/30' : 'bg-indigo-600/80 border-indigo-400/30'}`}>
                            {isRelocating ? 'DISPATCHING...' : 'MARSHAL'}
                        </div>
                    )}
                </Html>

                {showMenu && (
                    <Html position={[0, 0.6, 0]} center zIndexRange={[100, 0]} className="pointer-events-auto">
                        <div className="bg-slate-900 border border-slate-700 p-2 rounded-lg shadow-2xl flex flex-col gap-1 w-36 relative">
                            <div className="text-[10px] text-slate-400 font-mono mb-1 tracking-widest uppercase border-b border-white/10 pb-1">
                                Assign Patrol
                            </div>
                            {(Object.keys(PATROL_ZONES) as PatrolArea[]).map(zoneName => (
                                <button
                                    key={zoneName}
                                    className={`text-[10px] font-mono p-1.5 text-left rounded transition-colors ${area === zoneName ? 'text-emerald-400 bg-slate-800/80 font-bold border border-emerald-500/30' : 'text-slate-300 hover:bg-slate-800 border border-transparent'}`}
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setArea(zoneName);
                                        setShowMenu(false);
                                    }}
                                >
                                    {zoneName}
                                </button>
                            ))}
                        </div>
                    </Html>
                )}
            </mesh>
        </group>
    );
});

const StationEnvironment = React.memo(function StationEnvironment() {
    return (
        <group>
            {/* Interactive Crowd Marshals */}
            <PersonDot initialArea="Platform 1 (West)" />
            <PersonDot initialArea="Platform 1 (West)" />

            <PersonDot initialArea="Platform 2 (East)" />
            <PersonDot initialArea="Platform 2 (East)" />

            <PersonDot initialArea="Concourse" />
            <PersonDot initialArea="Concourse" />
            <PersonDot initialArea="Turnstiles" />

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
});

export const StationModel = React.memo(function StationModel({ devices, globalThreshold }: StationModelProps) {
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
});
