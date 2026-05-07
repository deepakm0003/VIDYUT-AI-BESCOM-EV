import React, { useState, useEffect, useRef } from 'react';
import { Bell, AlertTriangle, CheckCircle, Zap, Sliders } from 'lucide-react';
import { useAlertStream, useFeederStatus, useSchedulerOverride } from '../hooks/useAPI';
import { formatTimestamp } from '../utils/formatters';

export default function AlertConsole() {
  const [alerts, setAlerts] = useState([]);
  const [selectedFeeder, setSelectedFeeder] = useState(null);
  const [threshold, setThreshold] = useState(85);
  const [action, setAction] = useState('curtail');
  const [activeTab, setActiveTab] = useState('live');

  const { connected, lastAlert } = useAlertStream((newAlert) => {
    setAlerts(prev => [newAlert, ...prev.slice(0, 99)]);
  });

  const { feeders, lastUpdated } = useFeederStatus();
  const { loading: overrideLoading, error: overrideError, sendOverride } = useSchedulerOverride();

  const getSeverityColor = (severity) => {
    const colors = {
      'CRITICAL': 'bg-red-500/20 text-red-400 border-red-500/50',
      'WARNING': 'bg-orange-500/20 text-orange-400 border-orange-500/50',
      'INFO': 'bg-blue-500/20 text-blue-400 border-blue-500/50',
      'RESOLVED': 'bg-green-500/20 text-green-400 border-green-500/50'
    };
    return colors[severity] || 'bg-gray-500/20 text-gray-400 border-gray-500/50';
  };

  const getSeverityDotClass = (severity) => {
    switch (severity) {
      case 'CRITICAL':
        return 'bg-red-400';
      case 'WARNING':
        return 'bg-orange-400';
      case 'INFO':
        return 'bg-blue-400';
      case 'RESOLVED':
        return 'bg-green-400';
      default:
        return 'bg-gray-400';
    }
  };

  // Count alerts by severity
  const alertCounts = {
    total: alerts.length,
    critical: alerts.filter(a => a.type === 'CRITICAL').length,
    warning: alerts.filter(a => a.type === 'WARNING').length,
    safe: alerts.filter(a => a.type === 'RESOLVED').length
  };

  // Count feeders by status
  const feederCounts = {
    total: feeders?.length || 0,
    critical: feeders?.filter(f => f.load_pct > 92).length || 0,
    warning: feeders?.filter(f => f.load_pct > 85 && f.load_pct <= 92).length || 0,
    safe: feeders?.filter(f => f.load_pct <= 85).length || 0
  };

  const handleOverride = async () => {
    if (!selectedFeeder) return;

    try {
      await sendOverride(selectedFeeder, threshold, action);
      setAlerts(prev => [{
        alert_id: `override-${Date.now()}`,
        type: 'INFO',
        feeder_id: selectedFeeder,
        message: `Manual override executed: ${action} on ${selectedFeeder}`,
        load_pct: threshold,
        timestamp: new Date().toISOString(),
        action_taken: `${action} @ ${threshold}%`
      }, ...prev]);
    } catch (err) {
      console.error('Override failed:', err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`p-3 rounded-xl ${connected ? 'bg-green-500/10 animate-pulse' : 'bg-red-500/10'}`}>
            <Bell className={`w-6 h-6 ${connected ? 'text-green-400' : 'text-red-400'}`} />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-white">Alert Console</h2>
            <p className="text-sm text-gray-400">Real-time monitoring & feeder control</p>
          </div>
        </div>
        <div className="text-right">
          <div className={`text-sm font-semibold ${connected ? 'text-green-400' : 'text-red-400'}`}>
            {connected ? 'SSE Connected' : 'Disconnected'}
          </div>
          <p className="text-xs text-gray-400">Last update: {formatTimestamp(lastUpdated)}</p>
        </div>
      </div>

      {/* Live Counters */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-gradient-to-br from-red-500/10 to-red-500/5 border border-red-500/30 rounded-lg p-3">
          <p className="text-xs text-gray-400">CRITICAL Alerts</p>
          <p className="text-2xl font-bold text-red-400">{alertCounts.critical}</p>
        </div>
        <div className="bg-gradient-to-br from-orange-500/10 to-orange-500/5 border border-orange-500/30 rounded-lg p-3">
          <p className="text-xs text-gray-400">WARNING Alerts</p>
          <p className="text-2xl font-bold text-orange-400">{alertCounts.warning}</p>
        </div>
        <div className="bg-gradient-to-br from-green-500/10 to-green-500/5 border border-green-500/30 rounded-lg p-3">
          <p className="text-xs text-gray-400">Feeders Safe</p>
          <p className="text-2xl font-bold text-green-400">{feederCounts.safe}</p>
        </div>
        <div className="bg-gradient-to-br from-blue-500/10 to-blue-500/5 border border-blue-500/30 rounded-lg p-3">
          <p className="text-xs text-gray-400">Total Monitored</p>
          <p className="text-2xl font-bold text-blue-400">{feederCounts.total}</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-gray-700">
        {['live', 'feeders', 'override'].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 font-medium transition-all ${
              activeTab === tab
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-gray-400 hover:text-gray-300'
            }`}
          >
            {tab === 'live' && `📡 Live Alerts (${alertCounts.total})`}
            {tab === 'feeders' && `⚡ Feeder Status (${feederCounts.total})`}
            {tab === 'override' && '🎛️ Override Control'}
          </button>
        ))}
      </div>

      {/* Live Alerts Tab */}
      {activeTab === 'live' && (
        <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6 space-y-3 max-h-96 overflow-y-auto">
          {alerts.length === 0 ? (
            <div className="text-center py-8 text-gray-400">No alerts yet. System is stable.</div>
          ) : (
            alerts.map((alert) => (
              <div
                key={alert.alert_id}
                className={`border rounded-lg p-4 transition-all hover:shadow-lg ${getSeverityColor(alert.type)}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3 flex-1">
                    <span className={`w-2.5 h-2.5 rounded-full mt-2 ${getSeverityDotClass(alert.type)}`}></span>
                    <div className="flex-1">
                      <p className="font-semibold text-sm">{alert.message}</p>
                      <div className="flex items-center gap-3 mt-2 text-xs">
                        <span>Feeder: <strong>{alert.feeder_id}</strong></span>
                        <span>Load: <strong>{alert.load_pct}%</strong></span>
                        {alert.action_taken && <span>Action: <strong>{alert.action_taken}</strong></span>}
                      </div>
                    </div>
                  </div>
                  <p className="text-xs text-gray-400 whitespace-nowrap ml-2">{formatTimestamp(alert.timestamp)}</p>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Feeder Status Tab */}
      {activeTab === 'feeders' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {feeders?.slice(0, 10).map((feeder) => (
              <div
                key={feeder.feeder_id}
                className={`border rounded-lg p-4 transition-all cursor-pointer hover:shadow-lg ${
                  feeder.load_pct > 92
                    ? 'bg-red-500/10 border-red-500/50'
                    : feeder.load_pct > 85
                    ? 'bg-orange-500/10 border-orange-500/50'
                    : 'bg-green-500/10 border-green-500/50'
                }`}
                onClick={() => {
                  setSelectedFeeder(feeder.feeder_id);
                  setActiveTab('override');
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-semibold text-white">{feeder.feeder_id}</h4>
                  <span className={`text-xs font-bold px-2 py-1 rounded ${
                    feeder.load_pct > 92
                      ? 'bg-red-500/30 text-red-400'
                      : feeder.load_pct > 85
                      ? 'bg-orange-500/30 text-orange-400'
                      : 'bg-green-500/30 text-green-400'
                  }`}>
                    {feeder.load_pct > 92 ? 'CRITICAL' : feeder.load_pct > 85 ? 'WARNING' : 'SAFE'}
                  </span>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden mb-2">
                  <div
                    className={`h-full transition-all ${
                      feeder.load_pct > 92
                        ? 'bg-red-500'
                        : feeder.load_pct > 85
                        ? 'bg-orange-500'
                        : 'bg-green-500'
                    }`}
                    style={{ width: `${feeder.load_pct}%` }}
                  ></div>
                </div>
                <div className="flex justify-between text-xs text-gray-400">
                  <span>{feeder.load_pct}% Load</span>
                  <span>{formatTimestamp(feeder.last_updated)}</span>
                </div>
              </div>
            ))}
          </div>
          {feeders && feeders.length > 10 && (
            <p className="text-xs text-gray-400 text-center">... and {feeders.length - 10} more feeders</p>
          )}
        </div>
      )}

      {/* Override Control Tab */}
      {activeTab === 'override' && (
        <div className="bg-gradient-to-br from-purple-500/10 to-purple-500/5 border border-purple-500/30 rounded-xl p-6 space-y-4">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Sliders className="w-5 h-5 text-purple-400" />
            Feeder Override Control
          </h3>

          <div className="space-y-4">
            {overrideError && (
              <div className="p-3 rounded-lg border border-red-500/30 bg-red-500/10 text-sm text-red-300">
                {overrideError}
              </div>
            )}
            {/* Feeder Selection */}
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Select Feeder</label>
              <select
                value={selectedFeeder || ''}
                onChange={(e) => setSelectedFeeder(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              >
                <option value="">Choose a feeder...</option>
                {feeders?.map((f) => (
                  <option key={f.feeder_id} value={f.feeder_id}>
                    {f.feeder_id} ({f.load_pct}%)
                  </option>
                ))}
              </select>
            </div>

            {selectedFeeder && (
              <>
                {/* Threshold Control */}
                <div>
                  <label className="text-sm text-gray-400 mb-2 block">Threshold: {threshold}%</label>
                  <input
                    type="range"
                    min="50"
                    max="100"
                    value={threshold}
                    onChange={(e) => setThreshold(Number(e.target.value))}
                    className="w-full"
                  />
                </div>

                {/* Action Selection */}
                <div>
                  <label className="text-sm text-gray-400 mb-2 block">Action</label>
                  <div className="flex gap-3">
                    <button
                      onClick={() => setAction('curtail')}
                      className={`flex-1 py-2 rounded-lg font-semibold transition-all ${
                        action === 'curtail'
                          ? 'bg-red-500 text-white'
                          : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                      }`}
                    >
                      Curtail
                    </button>
                    <button
                      onClick={() => setAction('restore')}
                      className={`flex-1 py-2 rounded-lg font-semibold transition-all ${
                        action === 'restore'
                          ? 'bg-green-500 text-white'
                          : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                      }`}
                    >
                      Restore
                    </button>
                  </div>
                </div>

                {/* Summary */}
                <div className="bg-gray-900/60 rounded-lg p-4 border border-gray-700">
                  <p className="text-sm text-gray-300">
                    Will <strong>{action === 'curtail' ? 'reduce' : 'restore'}</strong> load on{' '}
                    <strong>{selectedFeeder}</strong> {action === 'curtail' ? 'when' : 'below'} load exceeds{' '}
                    <strong>{threshold}%</strong>
                  </p>
                </div>

                {/* Apply Button */}
                <button
                  onClick={handleOverride}
                  disabled={overrideLoading || !selectedFeeder}
                  className="w-full py-3 bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 rounded-lg font-semibold text-white transition-all hover:shadow-lg hover:shadow-purple-500/50"
                >
                  <Zap className="w-4 h-4 inline-block mr-2" />
                  {overrideLoading ? 'Applying...' : 'Apply Override'}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
