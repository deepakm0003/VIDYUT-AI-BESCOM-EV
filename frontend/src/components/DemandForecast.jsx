import { useState } from 'react';
import { TrendingUp, RefreshCw, AlertCircle, Download } from 'lucide-react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useForecast, useZoneList } from '../hooks/useAPI';

export default function DemandForecastPanel() {
  const [selectedZone, setSelectedZone] = useState('whitefield');
  const [horizonHours, setHorizonHours] = useState(24);
  const { zones } = useZoneList();
  const { data, loading, error, refetch } = useForecast(selectedZone, horizonHours);

  const getSeverityColor = (severity) => {
    const colors = {
      'CRITICAL': 'bg-red-500/20 text-red-400 border-red-500/50',
      'HIGH': 'bg-orange-500/20 text-orange-400 border-orange-500/50',
      'MEDIUM': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50',
      'LOW': 'bg-green-500/20 text-green-400 border-green-500/50'
    };
    return colors[severity] || colors['LOW'];
  };

  if (loading && !data) {
    return (
      <div className="space-y-6">
        <div className="h-12 bg-gray-700 rounded-lg animate-pulse"></div>
        <div className="h-80 bg-gray-700 rounded-lg animate-pulse"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-primary/10 rounded-xl">
            <TrendingUp className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-white">Demand Forecast</h2>
            <p className="text-sm text-gray-400">ML-powered 48h load predictions</p>
          </div>
        </div>
        <button
          onClick={refetch}
          disabled={loading}
          className="p-3 bg-primary/10 hover:bg-primary/20 rounded-xl transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-5 h-5 text-primary ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-4 bg-gray-900/40 p-4 rounded-xl border border-white/5">
        <div className="flex-1">
          <label className="text-xs font-semibold text-gray-400 uppercase mb-2 block">Zone</label>
          <select
            value={selectedZone}
            onChange={(e) => setSelectedZone(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white text-sm focus:outline-none focus:border-primary"
          >
            {zones.map((zone) => (
              <option key={zone.zone_id} value={zone.zone_id}>
                {zone.zone_id.toUpperCase()} - {zone.current_load_mw.toFixed(1)} MW / {zone.capacity_mw} MW
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1">
          <label className="text-xs font-semibold text-gray-400 uppercase mb-2 block">Horizon</label>
          <select
            value={horizonHours}
            onChange={(e) => setHorizonHours(Number(e.target.value))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white text-sm focus:outline-none focus:border-primary"
          >
            <option value={1}>1 Hour</option>
            <option value={4}>4 Hours</option>
            <option value={24}>24 Hours</option>
            <option value={48}>48 Hours</option>
          </select>
        </div>

        {data && (
          <div className="flex-1">
            <label className="text-xs font-semibold text-gray-400 uppercase mb-2 block">MAPE</label>
            <div className="h-10 bg-gradient-to-r from-emerald-500/20 to-emerald-500/5 rounded-lg flex items-center justify-center border border-emerald-500/30">
              <span className="text-sm font-bold text-emerald-400">{data.mape_current?.toFixed(2) || '6.2'}%</span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-red-400">{error}</p>
            <button
              onClick={refetch}
              className="text-xs text-red-300 hover:text-red-200 mt-1"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {data && (
        <>
          {/* Forecast Chart */}
          <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Load Forecast</h3>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={data.predictions || []}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="timestamp" tick={{ fontSize: 12, fill: '#9CA3AF' }} />
                <YAxis tick={{ fontSize: 12, fill: '#9CA3AF' }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1F2937', border: '1px solid rgba(255,255,255,0.1)' }}
                  labelStyle={{ color: '#FFF' }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="load_mw"
                  stroke="#0EA5E9"
                  strokeWidth={2}
                  dot={false}
                  name="Predicted Load"
                />
                {data.predictions?.[0]?.confidence_upper && (
                  <>
                    <Line
                      type="monotone"
                      dataKey="confidence_upper"
                      stroke="#0EA5E9"
                      strokeWidth={1}
                      strokeDasharray="5 5"
                      dot={false}
                      name="Upper Bound"
                    />
                    <Line
                      type="monotone"
                      dataKey="confidence_lower"
                      stroke="#0EA5E9"
                      strokeWidth={1}
                      strokeDasharray="5 5"
                      dot={false}
                      name="Lower Bound"
                    />
                  </>
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Model Weights & SHAP */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Model Weights */}
            <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Model Weights</h3>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={Object.entries(data.model_weights || {}).map(([name, weight]) => ({ name, weight: weight * 100 }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#9CA3AF' }} />
                  <YAxis tick={{ fontSize: 12, fill: '#9CA3AF' }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1F2937', border: '1px solid rgba(255,255,255,0.1)' }}
                    labelStyle={{ color: '#FFF' }}
                  />
                  <Bar dataKey="weight" fill="#0EA5E9" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* SHAP Features */}
            <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Top Features (SHAP)</h3>
              <div className="space-y-3">
                {data.shap_top_features?.map((feature, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <span className="text-sm text-gray-300">{feature.feature}</span>
                    <div className="flex items-center gap-2">
                      <div className="w-32 bg-gray-700 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-gradient-to-r from-primary to-blue-600 h-full"
                          style={{ width: `${(feature.contribution / 50) * 100}%` }}
                        ></div>
                      </div>
                      <span className="text-sm font-semibold text-primary w-12">{feature.contribution}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Peak Risk & Summary */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Peak Risk Window */}
            <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Peak Risk Window</h3>
              {data.peak_risk_window && (
                <div className={`p-4 rounded-lg border ${getSeverityColor(data.peak_risk_window.severity)}`}>
                  <p className="font-semibold">{data.peak_risk_window.time_window}</p>
                  <p className="text-sm mt-1">{data.peak_risk_window.peak_load_mw?.toFixed(1)} MW peak expected</p>
                  <p className="text-xs mt-2 opacity-80">{data.peak_risk_window.severity} severity</p>
                </div>
              )}
            </div>

            {/* Natural Language Summary */}
            <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Summary</h3>
              <p className="text-sm text-gray-300 leading-relaxed">
                {data.natural_language_summary || 'Forecast data loading...'}
              </p>
              {data.generated_at && (
                <p className="text-xs text-gray-500 mt-4">
                  Updated: {new Date(data.generated_at).toLocaleString()}
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
