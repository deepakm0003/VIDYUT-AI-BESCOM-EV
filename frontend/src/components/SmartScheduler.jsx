import { useEffect, useMemo, useState } from 'react';
import { Zap, Play, CheckCircle, AlertCircle, Gauge } from 'lucide-react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useScheduler, useZoneList, useFeederStatus } from '../hooks/useAPI';

export default function SmartSchedulerPanel() {
  const [selectedZone, setSelectedZone] = useState('whitefield');
  const [includeBMTC, setIncludeBMTC] = useState(false);
  const { zones } = useZoneList();
  const { result, loading, progress, runScheduler } = useScheduler();
  const { feeders } = useFeederStatus();

  const zoneOptions = useMemo(() => {
    if (zones && zones.length > 0) return zones;
    return [
      { zone_id: 'whitefield', current_load_mw: 0, capacity_mw: 150 },
      { zone_id: 'koramangala', current_load_mw: 0, capacity_mw: 120 },
      { zone_id: 'yelahanka', current_load_mw: 0, capacity_mw: 100 },
      { zone_id: 'bommanahalli', current_load_mw: 0, capacity_mw: 110 },
      { zone_id: 'hebbal', current_load_mw: 0, capacity_mw: 95 },
      { zone_id: 'indiranagar', current_load_mw: 0, capacity_mw: 105 }
    ];
  }, [zones]);

  useEffect(() => {
    if (!zoneOptions.find((z) => z.zone_id === selectedZone)) {
      setSelectedZone(zoneOptions[0]?.zone_id || 'whitefield');
    }
  }, [zoneOptions, selectedZone]);

  const handleRunScheduler = async () => {
    await runScheduler({
      zone_id: selectedZone,
      horizon_hours: 4,
      include_bmtc: includeBMTC
    });
  };

  const getStatusColor = (status) => {
    const colors = {
      'SHIFTED': 'bg-green-500/20 text-green-400 border-green-500/50',
      'PRIORITY': 'bg-blue-500/20 text-blue-400 border-blue-500/50',
      'CONFLICT': 'bg-red-500/20 text-red-400 border-red-500/50'
    };
    return colors[status] || colors['PRIORITY'];
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-primary/10 rounded-xl">
            <Zap className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-white">Smart Scheduler</h2>
            <p className="text-sm text-gray-400">MILP + RL-based load optimization</p>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-4 bg-gray-900/40 p-4 rounded-xl border border-white/5">
        <div className="flex-1">
          <label className="text-xs font-semibold text-gray-400 uppercase mb-2 block">Zone</label>
          <select
            value={selectedZone}
            onChange={(e) => setSelectedZone(e.target.value)}
            disabled={loading}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white text-sm focus:outline-none focus:border-primary disabled:opacity-50"
          >
            {zoneOptions.map((zone) => (
              <option key={zone.zone_id} value={zone.zone_id}>
                {zone.zone_id.toUpperCase()} - {zone.current_load_mw.toFixed(1)} MW / {zone.capacity_mw} MW
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-end gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={includeBMTC}
              onChange={(e) => setIncludeBMTC(e.target.checked)}
              disabled={loading}
              className="w-4 h-4 accent-primary"
            />
            <span className="text-sm text-gray-300">Include BMTC</span>
          </label>
        </div>

        <button
          onClick={handleRunScheduler}
          disabled={loading}
          className="flex items-center gap-2 px-6 py-2 bg-primary hover:bg-primary/80 text-white font-semibold rounded-lg transition-colors disabled:opacity-50 whitespace-nowrap"
        >
          <Play className="w-4 h-4" />
          {loading ? 'Running...' : 'Run Optimizer'}
        </button>
      </div>

      {/* Progress Steps */}
      {loading && progress && (
        <div className="bg-gradient-to-r from-primary/10 to-transparent border border-primary/30 rounded-xl p-6">
          <div className="space-y-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center font-semibold text-sm ${
                  i < progress.step 
                    ? 'bg-green-500 text-white' 
                    : i === progress.step - 1
                    ? 'bg-primary text-white animate-pulse'
                    : 'bg-gray-700 text-gray-400'
                }`}>
                  {i < progress.step ? '✓' : i + 1}
                </div>
                <div className="flex-1">
                  <p className={`text-sm font-semibold ${i < progress.step ? 'text-white' : 'text-gray-400'}`}>
                    {['PPO-RL Agent: Generating 48h power envelopes...', 'MILP Solver: Optimizing 127 EVs...', 'Digital Twin: Pre-validating signals...', 'EV Mithra: Pushing slot recommendations...'][i]}
                  </p>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-6 bg-gray-800 rounded-lg h-2 overflow-hidden">
            <div
              className="bg-gradient-to-r from-primary to-blue-600 h-full transition-all duration-300"
              style={{ width: `${progress.percent}%` }}
            ></div>
          </div>
          <p className="text-xs text-gray-400 text-center mt-3">{Math.round(progress.percent)}% Complete</p>
        </div>
      )}

      {result && !loading && (
        <>
          {/* Key Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-gray-900/40 border border-white/5 rounded-xl p-4">
              <p className="text-xs font-semibold text-gray-400 uppercase mb-2">Sessions Total</p>
              <p className="text-2xl font-bold text-white">{result.sessions_total}</p>
            </div>
            <div className="bg-gray-900/40 border border-white/5 rounded-xl p-4">
              <p className="text-xs font-semibold text-gray-400 uppercase mb-2">Sessions Shifted</p>
              <p className="text-2xl font-bold text-emerald-400">{result.sessions_shifted}</p>
            </div>
            <div className="bg-gray-900/40 border border-white/5 rounded-xl p-4">
              <p className="text-xs font-semibold text-gray-400 uppercase mb-2">Peak Reduction</p>
              <p className="text-2xl font-bold text-primary">{result.peak_reduction_pct?.toFixed(1) || 0}%</p>
            </div>
            <div className="bg-gray-900/40 border border-white/5 rounded-xl p-4">
              <p className="text-xs font-semibold text-gray-400 uppercase mb-2">Solve Time</p>
              <p className="text-2xl font-bold text-blue-400">{result.solve_time_ms}ms</p>
            </div>
          </div>

          {/* Before/After Chart */}
          <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Feeder Headroom (Before/After)</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={
                Object.keys(result.feeder_headroom_before || {}).map(feederId => ({
                  feeder: feederId,
                  before: result.feeder_headroom_before[feederId] || 0,
                  after: result.feeder_headroom_after[feederId] || 0
                }))
              }>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="feeder" tick={{ fontSize: 10, fill: '#9CA3AF' }} />
                <YAxis tick={{ fontSize: 12, fill: '#9CA3AF' }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1F2937', border: '1px solid rgba(255,255,255,0.1)' }}
                  labelStyle={{ color: '#FFF' }}
                />
                <Legend />
                <Bar dataKey="before" fill="#EF4444" radius={[8, 8, 0, 0]} />
                <Bar dataKey="after" fill="#10B981" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Sessions Table */}
          {result.assignments && result.assignments.length > 0 && (
            <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6 overflow-x-auto">
              <h3 className="text-lg font-semibold text-white mb-4">Charging Sessions</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left py-3 px-4 text-gray-400 font-semibold">EV ID</th>
                    <th className="text-left py-3 px-4 text-gray-400 font-semibold">Arrival</th>
                    <th className="text-left py-3 px-4 text-gray-400 font-semibold">Power (kW)</th>
                    <th className="text-left py-3 px-4 text-gray-400 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {result.assignments.slice(0, 5).map((session, i) => (
                    <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                      <td className="py-3 px-4 text-white">{session.ev_id || `EV-${i + 1}`}</td>
                      <td className="py-3 px-4 text-gray-300">{session.arrival_time || '14:00'}</td>
                      <td className="py-3 px-4 text-gray-300">{session.power_kw || 11}</td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-1 rounded text-xs font-semibold border ${getStatusColor(session.status)}`}>
                          {session.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.assignments.length > 5 && (
                <p className="text-xs text-gray-400 mt-4">+{result.assignments.length - 5} more sessions</p>
              )}
            </div>
          )}

          {/* BMTC Schedule */}
          {includeBMTC && result.bmtc_sequence && (
            <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4">BMTC Charging Timeline</h3>
              <div className="space-y-3">
                {result.bmtc_sequence.slice(0, 6).map((bus, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-gray-800/40 rounded-lg border border-white/5">
                    <div>
                      <p className="text-sm font-semibold text-white">{bus.bus_id || `Bus ${i + 1}`}</p>
                      <p className="text-xs text-gray-400">{bus.charge_start} - {bus.charge_end}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-primary">{bus.power_kw || 50}kW</p>
                      <p className="text-xs text-gray-400">Priority {bus.priority}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Digital Twin Validation */}
          {result.digital_twin_result && (
            <div className={`border rounded-xl p-6 ${
              result.digital_twin_result.overload_risk_pct < 5
                ? 'bg-green-500/10 border-green-500/30'
                : 'bg-orange-500/10 border-orange-500/30'
            }`}>
              <div className="flex items-start gap-3">
                <CheckCircle className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                  result.digital_twin_result.overload_risk_pct < 5 ? 'text-green-400' : 'text-orange-400'
                }`} />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-white mb-2">Digital Twin Validation</p>
                  <div className="space-y-1 text-xs text-gray-300">
                    <p>Overload Risk: {result.digital_twin_result.overload_risk_pct?.toFixed(1)}%</p>
                    <p>Voltage Sag: {result.digital_twin_result.voltage_sag_pct?.toFixed(1)}%</p>
                    <p>Status: {result.digital_twin_result.validated ? '✅ PASSED' : '⚠️ Review Needed'}</p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
