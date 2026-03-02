import { useEffect, useRef } from 'react';
import type { Packet } from '../types';
import { Database } from 'lucide-react';
import { format } from 'date-fns';
import { motion, AnimatePresence } from 'framer-motion';

interface RawPacketStreamProps {
    packets: Packet[];
}

export function RawPacketStream({ packets }: RawPacketStreamProps) {
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = 0;
        }
    }, [packets]);

    return (
        <div className="glass-panel overflow-hidden border-t-white/20 mt-6 shadow-[0_0_20px_rgba(0,0,0,0.5)]">
            <div className="p-3 border-b border-white/10 bg-black/40 flex items-center justify-between">
                <h3 className="font-mono text-xs uppercase tracking-widest flex items-center text-slate-300">
                    <Database size={14} className="mr-2 text-indigo-400" />
                    Raw Packet Stream
                </h3>
                {/* <div className="flex items-center text-[10px] text-emerald-400 font-mono">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 mr-2 shadow-[0_0_5px_rgba(16,185,129,0.8)]" />
                    LIVE
                </div> */}
            </div>

            <div
                ref={scrollRef}
                className="h-[120px] overflow-y-auto custom-scrollbar p-3 space-y-1 bg-[#010308] border-t border-white/5"
            >
                <AnimatePresence initial={false}>
                    {packets.map((packet) => (
                        <motion.div
                            key={packet.id}
                            initial={{ opacity: 0, x: -10, backgroundColor: 'rgba(255,255,255,0.1)' }}
                            animate={{ opacity: 1, x: 0, backgroundColor: 'rgba(0,0,0,0)' }}
                            transition={{ duration: 0.3 }}
                            className="font-mono text-[11px] py-1 px-2 rounded-sm flex items-start gap-3 hover:bg-white/5 transition-colors border-l-2 border-indigo-500/30 text-slate-400"
                        >
                            <div className="shrink-0 text-slate-500">
                                {format(new Date(packet.timestamp), 'HH:mm:ss')}
                            </div>
                            <div className="shrink-0 w-[55px] font-bold text-indigo-300">
                                {packet.device_id}
                            </div>
                            <div className="flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-slate-300">
                                <span className="text-slate-500">{'{'}</span>
                                <span className="text-emerald-400 ml-1">people_count:</span> <span className="text-amber-200">{packet.payload.people_count}</span>,
                                <span className="text-emerald-400 ml-2">density:</span> <span className="text-amber-200">{packet.payload.crowd_density.toFixed(2)}</span>,
                                <span className="text-emerald-400 ml-2">thr:</span> <span className="text-amber-200">{(packet.payload.threshold * 100).toFixed(0)}%</span>
                                <span className="text-slate-500 ml-1">{'}'}</span>
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>

                {packets.length === 0 && (
                    <div className="h-full flex items-center justify-center text-slate-600 font-mono text-sm opacity-50">
                        Awaiting telemetry interface packets...
                    </div>
                )}
            </div>
        </div>
    );
}
