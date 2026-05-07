import React, { useState } from 'react';
import './App.css';
import { useHealthCheck } from './hooks/useAPI';
import DemandForecast from './components/DemandForecast';
import SmartScheduler from './components/SmartScheduler';
import SiteIntelligence from './components/SiteIntelligence';
import CarbonCredits from './components/CarbonCredits';
import AlertConsole from './components/AlertConsole';

export default function App() {
  const [activeTab, setActiveTab] = useState('forecast');
  const { isHealthy, loading } = useHealthCheck();
  const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

  const handleDownloadReportPdf = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/report/submission-report.pdf`);
      if (!res.ok) throw new Error('Failed to download report');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'VIDYUT_AI_Submission_Report.pdf';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
    }
  };


  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <h1>VIDYUT AI</h1>
          <span className="subtitle">Theme 9 | BESCOM | PAN IIT AI for Bharat 2026</span>
        </div>
        <div className="header-right">
          <button
            onClick={handleDownloadReportPdf}
            className="px-3 py-2 rounded-lg text-sm font-semibold bg-white/5 hover:bg-white/10 border border-white/10 text-white"
            title="Download judge-ready PDF report"
          >
            Download Submission PDF
          </button>
          <div className="health-indicator">
            <div className={`status-dot ${isHealthy ? 'healthy' : 'unhealthy'}`}></div>
            <span className="health-text">
              {loading ? 'Checking...' : isHealthy ? 'Backend Connected' : 'Backend Offline'}
            </span>
          </div>
        </div>
      </header>

      <div className="app-container">
        {/* Sidebar */}
        <aside className="sidebar">
          <nav className="nav-menu">
            <button
              className={`nav-item ${activeTab === 'forecast' ? 'active' : ''}`}
              onClick={() => setActiveTab('forecast')}
            >
              Demand Forecast
            </button>
            <button
              className={`nav-item ${activeTab === 'scheduler' ? 'active' : ''}`}
              onClick={() => setActiveTab('scheduler')}
            >
              Smart Scheduler
            </button>
            <button
              className={`nav-item ${activeTab === 'sites' ? 'active' : ''}`}
              onClick={() => setActiveTab('sites')}
            >
              Site Intelligence
            </button>
            <button
              className={`nav-item ${activeTab === 'carbon' ? 'active' : ''}`}
              onClick={() => setActiveTab('carbon')}
            >
              Carbon Credits
            </button>
            <button
              className={`nav-item ${activeTab === 'alerts' ? 'active' : ''}`}
              onClick={() => setActiveTab('alerts')}
            >
              Alerts & Monitoring
            </button>
          </nav>
        </aside>

        {/* Main Content */}
        <main className="main-content">
          {activeTab === 'forecast' && <DemandForecast />}
          {activeTab === 'scheduler' && <SmartScheduler />}
          {activeTab === 'sites' && <SiteIntelligence />}
          {activeTab === 'carbon' && <CarbonCredits />}
          {activeTab === 'alerts' && <AlertConsole />}
        </main>
      </div>

      {/* Footer */}
      <footer className="app-footer">
        <p>VIDYUT AI v1.0.0 • Intelligent EV Charging Optimization & Infrastructure Planning for BESCOM</p>
      </footer>
    </div>
  );
}
