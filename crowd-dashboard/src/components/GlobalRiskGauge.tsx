import { motion } from 'framer-motion';
import type { TelemetryData } from '../types';
import { cn } from '../lib/utils';
import { Activity } from 'lucide-react';

interface GlobalRiskGaugeProps {
    devices: TelemetryData[];
}

export function GlobalRiskGauge({ devices }: GlobalRiskGaugeProps) {
    const activeDevices = devices.filter(d => d.status === 'active');
    const totalDensity = activeDevices.reduce((sum, d) => sum + d.metrics.crowd_density, 0);
    const averageDensity = activeDevices.length > 0 ? totalDensity / activeDevices.length : 0;

    const isHighRisk = averageDensity > 0.7;
    const isMediumRisk = averageDensity > 0.4 && averageDensity <= 0.7;

    const riskColor = isHighRisk
        ? 'text-red-500'
        : isMediumRisk
            ? 'text-amber-400'
            : 'text-emerald-400';

    const trackColor = isHighRisk
        ? 'var(--color-red-500)'
        : isMediumRisk
            ? 'var(--color-amber-400)'
            : 'var(--color-emerald-400)';

    return (
        <div className="glass-panel p-6 flex items-center w-full max-w-2xl mx-auto mb-6">
            <div className="flex flex-col items-center justify-center mr-8 border-r border-white/10 pr-8">
                <Activity size={32} className={cn("mb-2", riskColor)} />
                <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-widest text-center whitespace-nowrap">
                    Global Risk
                    <br />
                    Index
                </h2>
            </div>

            <div className="flex-1 flex flex-col justify-center">
                <div className="flex justify-between items-end mb-2">
                    <span className="text-4xl font-mono font-bold text-white tracking-tighter">
                        <motion.span>
                            {(averageDensity * 100).toFixed(1)}
                        </motion.span>
                        <span className="text-xl text-slate-500 ml-1">%</span>
                    </span>
                    <span className={cn("text-xs uppercase font-bold tracking-widest px-2 py-1 bg-white/5 rounded", riskColor)}>
                        {isHighRisk ? 'Critical' : isMediumRisk ? 'Elevated' : 'Nominal'}
                    </span>
                </div>

                {/* Linear Gauge */}
                <div className="h-4 w-full bg-slate-900 rounded-full overflow-hidden border border-white/5 relative">
                    <motion.div
                        className="absolute top-0 left-0 bottom-0 shadow-[0_0_10px_currentColor]"
                        initial={{ width: 0 }}
                        animate={{
                            width: `${Math.min(100, averageDensity * 100)}%`,
                            backgroundColor: isHighRisk ? '#ef4444' : isMediumRisk ? '#fbbf24' : '#34d399'
                        }}
                        transition={{ type: "spring", stiffness: 60, damping: 20 }}
                    />
                    {/* Threshold marker for Global Average (e.g. 70%) */}
                    <div className="absolute top-0 bottom-0 left-[70%] border-l border-white/40 border-dashed z-10" />
                </div>
                <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-1">
                    <span>0%</span>
                    <span>Avg Density</span>
                    <span>100%</span>
                </div>
            </div>
        </div>
    );
}
