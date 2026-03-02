import { useEffect, useRef } from 'react';
import type { LogEntry } from '../types';
import { Terminal, ShieldAlert, Activity, Wifi } from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '../lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

interface LiveActivityLogProps {
    logs: LogEntry[];
}

export function LiveActivityLog({ logs }: LiveActivityLogProps) {
    const scrollRef = useRef<HTMLDivElement>(null);

    // Auto-scroll to top since our new logs are unshifted to the start
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = 0;
        }
    }, [logs]);

    return (
        <div className="glass-panel overflow-hidden border-t-white/20 mt-6 shadow-[0_0_20px_rgba(0,0,0,0.5)]">
            <div className="p-3 border-b border-white/10 bg-black/40 flex items-center justify-between">
                <h3 className="font-mono text-xs uppercase tracking-widest flex items-center text-slate-300">
                    <Terminal size={14} className="mr-2 text-indigo-400" />
                    Raw Packet Feed
                </h3>
                
            </div>

            <div
                ref={scrollRef}
                className="h-[120px] overflow-y-auto custom-scrollbar p-3 space-y-1 bg-[#010308] border-t border-white/5"
            >
                <AnimatePresence initial={false}>
                    {logs.map((log) => {
                        const isCritical = log.event_type === 'CRITICAL_ALERT';
                        const isStatus = log.event_type === 'STATUS_CHANGE';

                        return (
                            <motion.div
                                key={log.id}
                                initial={{ opacity: 0, x: -10, backgroundColor: 'rgba(255,255,255,0.1)' }}
                                animate={{ opacity: 1, x: 0, backgroundColor: 'rgba(0,0,0,0)' }}
                                transition={{ duration: 0.3 }}
                                className={cn(
                                    "font-mono text-xs py-1.5 px-2 rounded-sm flex items-start gap-4 hover:bg-white/5 transition-colors border-l-2",
                                    isCritical ? "border-red-500 text-red-200 bg-red-500/5" :
                                        isStatus ? "border-amber-400 text-amber-200" :
                                            "border-white/10 text-slate-400"
                                )}
                            >
                                <div className="flex-shrink-0 text-slate-500 w-[65px]">
                                    {format(new Date(log.timestamp), 'HH:mm:ss')}
                                </div>

                                <div className="flex-shrink-0 w-6 flex justify-center">
                                    {isCritical ? <ShieldAlert size={14} className="text-red-500" /> :
                                        isStatus ? <Wifi size={14} className="text-amber-400" /> :
                                            <Activity size={12} className="text-slate-500 mt-0.5" />}
                                </div>

                                <div className="flex-shrink-0 w-[70px] font-bold text-slate-300">
                                    {log.device_id}
                                </div>

                                <div className={cn(
                                    "flex-1",
                                    isCritical && "text-red-400 font-semibold"
                                )}>
                                    {log.message}
                                </div>
                            </motion.div>
                        );
                    })}
                </AnimatePresence>

                {logs.length === 0 && (
                    <div className="h-full flex items-center justify-center text-slate-600 font-mono text-sm opacity-50">
                        Awaiting generic telemetry interface packets...
                    </div>
                )}
            </div>
        </div>
    );
}
