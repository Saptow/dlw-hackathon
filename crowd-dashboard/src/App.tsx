import { useTelemetrySimulator } from './hooks/useTelemetrySimulator';
import { SystemHealthSidebar } from './components/SystemHealthSidebar';
import { GlobalRiskGauge } from './components/GlobalRiskGauge';
import { ZoneCard } from './components/ZoneCard';
import { LiveActivityLog } from './components/LiveActivityLog';
import { RawPacketStream } from './components/RawPacketStream';

function App() {
  const { devices, logs, packets } = useTelemetrySimulator();

  return (
    <div className="h-screen w-full bg-brand-bg flex font-sans text-slate-200 overflow-hidden">
      {/* Sidebar fixed to the right or left */}
      <SystemHealthSidebar devices={devices} />

      {/* Main Dashboard Content */}
      <main className="flex-1 p-6 md:p-8 overflow-y-auto custom-scrollbar relative h-full">
        {/* Decorative Grid Background for Command Center Feel */}
        <div className="fixed inset-0 pointer-events-none opacity-20" style={{ backgroundImage: 'radial-gradient(var(--color-slate-800) 1px, transparent 1px)', backgroundSize: '40px 40px' }} />

        <div className="relative z-10 max-w-7xl mx-auto flex flex-col h-full">
          <header className="mb-8 flex justify-between items-end">
            <div>
              <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-white mb-2 flex items-center shadow-black drop-shadow-lg">
                <span className="bg-red-500 w-3 h-3 rounded-full mr-3 animate-pulse shadow-[0_0_10px_rgba(239,68,68,0.8)]" />
                Operations Command Center
              </h1>
              <p className="text-slate-400 font-mono text-xs md:text-sm uppercase tracking-widest pl-6">
                Live Telemetry Feed & Crowd Control Density Grid
              </p>
            </div>
            {/* Optional Header Actions */}
            <div className="hidden md:flex text-slate-500 font-mono text-[10px] space-x-4">
              <span>SYSTEM: ONLINE</span>
              <span>UPLINK: SECURE</span>
            </div>
          </header>

          <GlobalRiskGauge devices={devices} />

          {/* Bento Grid layout */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 auto-rows-[300px]">
            {devices.map((device) => (
              <ZoneCard key={device.device_id} data={device} />
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
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
