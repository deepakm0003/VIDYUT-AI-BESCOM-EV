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

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <h1>⚡ VIDYUT AI</h1>
          <span className="subtitle">EV Grid Optimization Platform</span>
        </div>
        <div className="header-right">
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
              📊 Demand Forecast
            </button>
            <button
              className={`nav-item ${activeTab === 'scheduler' ? 'active' : ''}`}
              onClick={() => setActiveTab('scheduler')}
            >
              🔄 Smart Scheduler
            </button>
            <button
              className={`nav-item ${activeTab === 'sites' ? 'active' : ''}`}
              onClick={() => setActiveTab('sites')}
            >
              📍 Site Intelligence
            </button>
            <button
              className={`nav-item ${activeTab === 'carbon' ? 'active' : ''}`}
              onClick={() => setActiveTab('carbon')}
            >
              💚 Carbon Credits
            </button>
            <button
              className={`nav-item ${activeTab === 'alerts' ? 'active' : ''}`}
              onClick={() => setActiveTab('alerts')}
            >
              🚨 Alerts & Monitoring
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
        <p>VIDYUT AI v1.0.0 • Machine Learning Optimization for EV Grid Integration</p>
      </footer>
    </div>
  );
}
