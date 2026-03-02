import type { TelemetryData } from '../types';
import { Clock, Server, AlertCircle } from 'lucide-react';
import { cn } from '../lib/utils';
import { format } from 'date-fns';

interface SystemHealthSidebarProps {
    devices: TelemetryData[];
}

export function SystemHealthSidebar({ devices }: SystemHealthSidebarProps) {
    const activeCount = devices.filter(d => d.status === 'active').length;
    const criticalCount = devices.filter(d => d.status === 'active' && d.metrics.crowd_density > d.metrics.threshold).length;
    const nonActiveCount = devices.length - activeCount;

    return (
        <aside className="w-80 glass-panel flex flex-col h-full overflow-hidden shrink-0">
            <div className="p-5 border-b border-white/10">
                <h2 className="text-xl font-bold tracking-wide flex items-center text-white">
                    <Server className="mr-2 text-indigo-400" size={20} />
                    System Health
                </h2>

                <div className="mt-4 grid grid-cols-3 gap-2">
                    <div className="bg-slate-900/50 p-2 rounded-lg text-center border border-white/5">
                        <span className="block text-xl font-mono text-emerald-400">{activeCount}</span>
                        <span className="text-[10px] uppercase text-slate-400 font-semibold tracking-wider">Active</span>
                    </div>
                    <div className="bg-slate-900/50 p-2 rounded-lg text-center border border-white/5">
                        <span className="block text-xl font-mono text-amber-400">{nonActiveCount}</span>
                        <span className="text-[10px] uppercase text-slate-400 font-semibold tracking-wider">Issues</span>
                    </div>
                    <div className="bg-slate-900/50 p-2 rounded-lg text-center border border-white/5">
                        <span className="block text-xl font-mono text-red-500">{criticalCount}</span>
                        <span className="text-[10px] uppercase text-slate-400 font-semibold tracking-wider">Alerts</span>
                    </div>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
                {devices.map((device) => {
                    const isCritical = device.status === 'active' && device.metrics.crowd_density > device.metrics.threshold;

                    return (
                        <div
                            key={device.device_id}
                            className={cn(
                                "p-3 rounded-lg border flex flex-col gap-2 transition-all",
                                device.status === 'active'
                                    ? isCritical
                                        ? "bg-red-500/10 border-red-500/30"
                                        : "bg-white/5 border-white/10 hover:bg-white/10"
                                    : "bg-slate-900/80 border-slate-800 grayscale opacity-80"
                            )}
                        >
                            <div className="flex justify-between items-center">
                                <div className="flex items-center">
                                    <span className={cn(
                                        "w-2 h-2 rounded-full mr-2 shadow-[0_0_5px_currentColor]",
                                        device.status === 'active' ? "bg-emerald-400 text-emerald-400" :
                                            device.status === 'offline' ? "bg-slate-500 text-slate-500" :
                                                "bg-amber-400 text-amber-400"
                                    )} />
                                    <span className="font-mono text-sm font-semibold">{device.device_id}</span>
                                </div>
                                {isCritical && <AlertCircle size={14} className="text-red-400" />}
                            </div>

                            <div className="text-xs text-slate-300 truncate">
                                {device.location_label}
                            </div>

                            <div className="flex justify-between items-center text-[10px] text-slate-500 font-mono mt-1 pt-2 border-t border-white/5">
                                <span className="flex items-center">
                                    <Clock size={10} className="mr-1" />
                                    {format(new Date(device.timestamp), 'HH:mm:ss')}
                                </span>
                                <span className="uppercase tracking-widest">{device.status}</span>
                            </div>
                        </div>
                    );
                })}
            </div>
        </aside>
    );
}
