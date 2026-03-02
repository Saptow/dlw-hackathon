import { useState } from 'react';
// import { usePresentationSimulator } from './hooks/usePresentationSimulator';
import { useTelemetryStream } from './hooks/useTelemetryStream';
import { ZoneCard } from './components/ZoneCard';
import { LiveActivityLog } from './components/LiveActivityLog';
import { RawPacketStream } from './components/RawPacketStream';
import { StationModel } from './components/StationModel';

function App() {
  const [globalThreshold, setGlobalThreshold] = useState(0.5);

  // Use the presentation simulator instead of live websockets for the demo
  //const { devices, logs, packets } = usePresentationSimulator(globalThreshold);
  const { devices, logs, packets } = useTelemetryStream('ws://localhost:8080/ws');

  return (
    <div className="h-screen w-full bg-brand-bg flex font-sans text-slate-200 overflow-hidden">

      {/* Main Dashboard Content */}
      <main className="flex-1 p-6 md:p-8 overflow-y-auto custom-scrollbar relative h-full">
        {/* Decorative Grid Background for Command Center Feel */}
        <div className="fixed inset-0 pointer-events-none opacity-20" style={{ backgroundImage: 'radial-gradient(var(--color-slate-800) 1px, transparent 1px)', backgroundSize: '40px 40px' }} />

        <div className="relative z-10 max-w-7xl mx-auto flex flex-col h-full">
          <header className="mb-8 flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
            <div>
              {/* <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-white mb-2 flex items-center shadow-black drop-shadow-lg">
                Operations Command Center
              </h1> */}
              <p className="text-slate-400 font-mono text-xs md:text-sm uppercase tracking-widest">
                Live Feed & Crowd Control Grid
              </p>
            </div>

            {/* Global Threshold Control */}
            <div className="flex flex-col sm:flex-row items-center gap-3 bg-slate-900/50 px-4 py-2.5 rounded-xl border border-white/5 shadow-inner">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-400 whitespace-nowrap">
                Risk Limit: <span className="text-white ml-1">{Math.round(globalThreshold * 100)}%</span>
              </label>
              <input
                type="range"
                min="0.1"
                max="1"
                step="0.05"
                value={globalThreshold}
                onChange={(e) => setGlobalThreshold(parseFloat(e.target.value))}
                className="w-32 md:w-48 accent-red-500 hover:accent-red-400 cursor-pointer"
              />
            </div>
          </header>


          {/* Dashboard Layout */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 auto-rows-[300px]">
            {/* 3D Station Digital Twin (Featured Span) */}
            <div className="md:col-span-2 lg:col-span-2 xl:col-span-2 row-span-1 md:row-span-2 rounded-2xl overflow-hidden ring-1 ring-white/10 shadow-xl bg-slate-900/50">
              <StationModel devices={devices} globalThreshold={globalThreshold} />
            </div>

            {/* Zone Cards */}
            {devices.map((device) => (
              <ZoneCard key={device.device_id} data={device} globalThreshold={globalThreshold} />
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-4">
            <LiveActivityLog logs={logs} />
            <RawPacketStream packets={packets} />
          </div>

          {/* Spacer for bottom padding */}
          <div className="h-10 w-full shrink-0" />
        </div>
      </main>
    </div>
  );
}

export default App;
