import React, { useState, useEffect } from 'react';
import { TrendingUp, Download, Award, Leaf, BarChart3 } from 'lucide-react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useCarbonSummary, useCarbonMonthly, useCarbonCertificate } from '../hooks/useAPI';
import { formatCurrency, formatNumber, formatEnergy, formatCO2 } from '../utils/formatters';

export default function CarbonCredits() {
  const [selectedMonth, setSelectedMonth] = useState(new Date().toISOString().slice(0, 7));
  const [projectionYears, setProjectionYears] = useState(1);
  
  const { summary, loading: summaryLoading } = useCarbonSummary();
  const { monthly, loading: monthlyLoading } = useCarbonMonthly();
  const { certificate, loading: certLoading } = useCarbonCertificate(selectedMonth);

  // Calculate revenue projection
  const projectedRevenue = summary ? summary.revenue_crore * projectionYears * 1.05 : 0;
  const monthlyData = monthly || [];
  const avgMonthly = monthlyData.length > 0 ? monthlyData.reduce((sum, m) => sum + m.revenue_crore, 0) / monthlyData.length : 0;

  const handleDownloadCert = () => {
    if (certificate) {
      const element = document.createElement('a');
      element.href = certificate.download_url;
      element.download = `BEE_Certificate_${selectedMonth}.pdf`;
      document.body.appendChild(element);
      element.click();
      document.body.removeChild(element);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-green-500/10 rounded-xl animate-pulse">
            <Leaf className="w-6 h-6 text-green-400" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-white">Carbon Credits</h2>
            <p className="text-sm text-gray-400">Emissions reduction & monetization analytics</p>
          </div>
        </div>
      </div>

      {/* Hero Stats */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[
            { label: 'Total MWh Shifted', value: formatNumber(summary.total_mwh_shifted), icon: '⚡', color: 'from-blue-500/20 to-blue-500/5', border: 'border-blue-500/30' },
            { label: 'CO₂ Avoided', value: formatCO2(summary.co2_avoided_tonnes), icon: '🌍', color: 'from-green-500/20 to-green-500/5', border: 'border-green-500/30' },
            { label: 'Revenue Earned', value: formatCurrency(summary.revenue_crore * 1e7), icon: '💚', color: 'from-emerald-500/20 to-emerald-500/5', border: 'border-emerald-500/30' },
            { label: 'Months Tracked', value: summary.months_tracked, icon: '📅', color: 'from-purple-500/20 to-purple-500/5', border: 'border-purple-500/30' }
          ].map((stat, i) => (
            <div key={i} className={`bg-gradient-to-br ${stat.color} border ${stat.border} rounded-xl p-4 transform hover:scale-105 transition-all`}>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs text-gray-400 mb-1">{stat.label}</p>
                  <p className="text-xl font-bold text-white">{stat.value}</p>
                </div>
                <span className="text-2xl">{stat.icon}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Monthly Breakdown */}
        <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-green-400" />
            Monthly Breakdown
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={monthlyData.slice(-12)}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#9CA3AF' }} />
              <YAxis tick={{ fontSize: 11, fill: '#9CA3AF' }} />
              <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid rgba(255,255,255,0.1)' }} />
              <Legend />
              <Bar dataKey="mwh_shifted" fill="#0EA5E9" name="MWh Shifted" radius={[8, 8, 0, 0]} />
              <Bar dataKey="revenue_crore" fill="#10B981" name="Revenue (Cr)" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Revenue Projection */}
        <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
            Revenue Projection
          </h3>
          
          <div className="space-y-4">
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Years to Project</label>
              <div className="flex gap-2">
                {[1, 3, 5, 10].map((yr) => (
                  <button
                    key={yr}
                    onClick={() => setProjectionYears(yr)}
                    className={`px-4 py-2 rounded-lg font-semibold transition-all ${
                      projectionYears === yr
                        ? 'bg-emerald-500 text-white'
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    {yr}y
                  </button>
                ))}
              </div>
            </div>

            <div className="bg-gradient-to-r from-emerald-500/20 to-emerald-500/5 border border-emerald-500/30 rounded-lg p-4">
              <p className="text-sm text-gray-400 mb-1">Projected Revenue ({projectionYears}-year)</p>
              <p className="text-3xl font-bold text-emerald-400">{formatCurrency(projectedRevenue * 1e7)}</p>
              <p className="text-xs text-gray-400 mt-2">With 5% annual growth</p>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="bg-gray-800/50 rounded p-3">
                <p className="text-gray-400 text-xs mb-1">Current Annual Rate</p>
                <p className="font-bold text-white">{formatCurrency(avgMonthly * 12 * 1e7)}/yr</p>
              </div>
              <div className="bg-gray-800/50 rounded p-3">
                <p className="text-gray-400 text-xs mb-1">Est. Carbon Price</p>
                <p className="font-bold text-green-400">₹500/T CO₂</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Certificate Generator */}
      <div className="bg-gradient-to-br from-purple-500/10 to-purple-500/5 border border-purple-500/30 rounded-xl p-6">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Award className="w-5 h-5 text-purple-400" />
          BEE Certificate Generator
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-sm text-gray-400 mb-2 block">Select Month</label>
            <input
              type="month"
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            />
          </div>

          <div>
            <label className="text-sm text-gray-400 mb-2 block">&nbsp;</label>
            <button
              onClick={handleDownloadCert}
              disabled={certLoading || !certificate}
              className="w-full flex items-center justify-center gap-2 py-2 bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 disabled:opacity-50 rounded-lg font-semibold text-white transition-all"
            >
              <Download className="w-4 h-4" />
              {certLoading ? 'Generating...' : 'Download Certificate'}
            </button>
          </div>
        </div>

        {certificate && (
          <div className="mt-4 p-4 bg-gray-900/40 rounded-lg border border-purple-500/20">
            <p className="text-sm text-gray-300">
              <strong>Certificate ID:</strong> {certificate.certificate_id}
            </p>
            <p className="text-sm text-gray-300 mt-2">
              <strong>Issued by:</strong> Bureau of Energy Efficiency (BEE)
            </p>
            <p className="text-sm text-gray-300 mt-2">
              <strong>MWh Shifted:</strong> {formatEnergy(certificate.mwh_shifted)}
            </p>
          </div>
        )}
      </div>

      {/* Peer Comparison */}
      <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6">
        <h3 className="text-lg font-semibold text-white mb-4">Peer Comparison Metrics</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            { label: 'vs Peer Average', value: '+32%', color: 'text-green-400', icon: '📈' },
            { label: 'Industry Rank', value: '#8', color: 'text-blue-400', icon: '🏆' },
            { label: 'Growth vs Last Year', value: '+45%', color: 'text-emerald-400', icon: '🚀' }
          ].map((metric, i) => (
            <div key={i} className="bg-gray-800/50 rounded-lg p-4 text-center hover:bg-gray-800 transition-all">
              <span className="text-3xl mb-2 block">{metric.icon}</span>
              <p className="text-xs text-gray-400 mb-1">{metric.label}</p>
              <p className={`text-2xl font-bold ${metric.color}`}>{metric.value}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
