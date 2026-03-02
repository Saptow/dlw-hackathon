import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { formatDistanceToNowStrict } from 'date-fns';
import { AlertTriangle, WifiOff, EyeOff, HelpCircle } from 'lucide-react';
import type { TelemetryData } from '../types';
import { cn } from '../lib/utils';

interface ZoneCardProps {
    data: TelemetryData;
    globalThreshold: number;
}

export function ZoneCard({ data, globalThreshold }: ZoneCardProps) {
    const [dataAge, setDataAge] = useState<string>('just now');

    useEffect(() => {
        const interval = setInterval(() => {
            setDataAge(formatDistanceToNowStrict(new Date(data.timestamp), { addSuffix: true }));
        }, 1000);
        return () => clearInterval(interval);
    }, [data.timestamp]);

    const { metrics, status, location_label, device_id } = data;
    // Threshold now acts as the dynamic "Risk of Crush" index (0 to 1)
    const isCritical = metrics.threshold >= globalThreshold;
    const isReliable = status === 'active';

    const liquidHeight = `${Math.min(100, Math.max(0, metrics.threshold * 100))}%`;
    const riskLimitPosition = `${globalThreshold * 100}%`;

    return (
        <div
            className={cn(
                "glass-panel relative overflow-hidden transition-all duration-500 shadow-md",
                isCritical && isReliable ? "ring-2 ring-red-500/80 " : "border-white/10"
            )}
        >
            {/* Background Pulse for Critical State */}
            {isCritical && isReliable && (
                <div
                    className="absolute inset-0 bg-red-500/10 pointer-events-none"
                />
            )}

            <div className="p-5 flex flex-col h-full z-10 relative">
                {/* Header */}
                <div className="flex justify-between items-start mb-4 h-12"> {/* Fixed Height added here */}
                    <div>
                        <h3 className="font-semibold text-lg text-slate-100 tracking-wide truncate w-40">
                            {location_label}
                        </h3>
                        <p className="text-xs text-slate-400 font-mono mt-0.5">{device_id}</p>
                    </div>

                    {/* Wrap the badge area in a container that reserves space */}
                    <div className="flex items-center justify-end h-8 min-w-[80px]">
                        {!isReliable ? (
                            <span className="flex items-center text-xs text-amber-400 bg-amber-400/10 px-2 py-1 rounded-full border border-amber-400/20">
                                {status === 'offline' && <WifiOff size={12} className="mr-1" />}
                                {status === 'obscured' && <EyeOff size={12} className="mr-1" />}
                                {status === 'uncertain' && <HelpCircle size={12} className="mr-1" />}
                                <span className="uppercase tracking-wider font-semibold text-[10px]">{status}</span>
                            </span>
                        ) : isCritical ? (
                            <motion.div
                                animate={{ scale: [1, 1.2, 1] }}
                                transition={{ duration: 0.8, repeat: Infinity }}
                                className="text-red-500"
                            >
                                <AlertTriangle size={20} />
                            </motion.div>
                        ) : (
                            // This invisible div keeps the space occupied when everything is "Normal"
                            <div className="w-5 h-5" />
                        )}
                    </div>
                </div>
                {/* Unreliable Data Filter Area */}
                <div className={cn("flex-1 flex flex-col transition-all duration-700", !isReliable && "grayscale opacity-60")}>
                    <div className="flex items-end justify-between mb-2">
                        <div className="flex flex-col">
                            <span className="text-3xl font-bold font-mono text-white">
                                {metrics.people_count}
                            </span>
                            <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
                                People Count
                            </span>
                        </div>
                        <div className="flex flex-col items-end">
                            <span className={cn(
                                "text-lg font-bold font-mono",
                                isCritical ? "text-red-400" : "text-emerald-400"
                            )}>
                                {metrics.crowd_density.toFixed(2)}
                            </span>
                            <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
                                PPL / M²
                            </span>
                        </div>
                    </div>

                    {/* Liquid Progress Bar */}
                    <div className="relative h-20 w-full bg-slate-900/50 rounded-lg overflow-hidden mt-auto border border-white/5">
                        {/* Critical Risk Limit Marker */}
                        {/* <div
                            className="absolute left-0 right-0 border-b border-dashed border-red-500/60 z-20 transition-all duration-300"
                            style={{ bottom: riskLimitPosition }}
                        >
                            <span className="absolute right-1 -top-4 text-[10px] text-red-400 font-mono bg-slate-950/80 px-1 rounded">
                                LIMIT {Math.round(globalThreshold * 100)}%
                            </span>
                        </div> */}

                        <div
                            className="absolute left-0 right-0 border-b border-dashed border-red-500/60 z-20 transition-all duration-300"
                            style={{ bottom: riskLimitPosition }}
                        >
                            <span className={cn(
                                "absolute right-1 text-[10px] text-red-400 font-mono bg-slate-950/80 px-1 rounded transition-all duration-300",
                                // If threshold is high, move label below the line to prevent cutoff
                                globalThreshold > 0.8 ? "top-1" : "-top-4"
                            )}>
                                LIMIT {Math.round(globalThreshold * 100)}%
                            </span>
                        </div>

                        {/* Liquid Fill */}
                        <motion.div
                            className={cn(
                                "absolute bottom-0 left-0 right-0 w-full z-10",
                                isCritical ? "bg-linear-to-t from-red-600 to-red-400" : "bg-linear-to-t from-emerald-600 to-emerald-400"
                            )}
                            initial={{ height: 0 }}
                            animate={{ height: liquidHeight }}
                            transition={{ type: "spring", stiffness: 50, damping: 15 }}
                        >
                            {/* Fake ripples effect via pseudo elements or additional divs */}
                            <div className="absolute top-0 left-0 right-0 h-1  blur-[1px]" />
                        </motion.div>
                    </div>
                </div>

                {/* Footer */}
                <div className="mt-4 pt-2 border-t border-white/10 flex justify-between items-center text-xs text-slate-400 font-mono">
                    <span>Data Age</span>
                    <span>{dataAge}</span>
                </div>
            </div>
        </div>
    );
}
