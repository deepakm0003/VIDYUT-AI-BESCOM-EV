/**
 * VIDYUT AI Custom React Hooks
 * All API calls to FastAPI backend at http://localhost:8000
 */

import { useState, useEffect, useCallback, useRef } from 'react';

const API_BASE = 'http://localhost:8000/api';

// ==================== FORECAST HOOKS ====================

export const useForecast = (zoneId, horizonHours) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchForecast = useCallback(async () => {
    if (!zoneId || !horizonHours) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_BASE}/api/forecast/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          zone_id: zoneId,
          horizon_hours: horizonHours
        })
      });
      
      if (!response.ok) {
        throw new Error(`Forecast API error: ${response.statusText}`);
      }
      
      const result = await response.json();
      setData(result);
    } catch (err) {
      setError(err.message);
      console.error('Forecast fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [zoneId, horizonHours]);

  useEffect(() => {
    fetchForecast();
  }, [fetchForecast]);

  return { data, loading, error, refetch: fetchForecast };
};

export const useZoneList = () => {
  const [zones, setZones] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchZones = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/forecast/zones`);
        if (!response.ok) throw new Error('Failed to fetch zones');
        const result = await response.json();
        setZones(result.zones || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    
    fetchZones();
  }, []);

  return { zones, loading, error };
};

export const useForecastAccuracy = () => {
  const [metrics, setMetrics] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchAccuracy = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/forecast/accuracy`);
        if (response.ok) {
          const result = await response.json();
          setMetrics(result.metrics || []);
        }
      } catch (err) {
        console.error('Accuracy fetch error:', err);
      } finally {
        setLoading(false);
      }
    };
    
    fetchAccuracy();
  }, []);

  return { metrics, loading };
};

// ==================== SCHEDULER HOOKS ====================

export const useScheduler = () => {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(null);

  const runScheduler = useCallback(async (params) => {
    setLoading(true);
    setError(null);
    setProgress(0);

    try {
      // Simulate progress steps for UI feedback
      const steps = [
        { step: 1, message: 'PPO-RL Agent: Generating 48h power envelopes...', delay: 500 },
        { step: 2, message: 'MILP Solver (HiGHS): Optimizing 127 EVs across 12 stations...', delay: 1000 },
        { step: 3, message: 'Digital Twin: Pre-validating curtailment signals...', delay: 800 },
        { step: 4, message: 'EV Mithra: Pushing slot recommendations...', delay: 500 }
      ];

      for (const { step, message, delay } of steps) {
        setProgress({ step, message, percent: (step / steps.length) * 100 });
        await new Promise(resolve => setTimeout(resolve, delay));
      }

      const response = await fetch(`${API_BASE}/api/scheduler/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          zone_id: params.zone_id,
          horizon_hours: params.horizon_hours || 4,
          include_bmtc: params.include_bmtc || false
        })
      });

      if (!response.ok) {
        throw new Error(`Scheduler API error: ${response.statusText}`);
      }

      const data = await response.json();
      setResult(data);
      setProgress({ step: 4, message: 'Optimization complete!', percent: 100 });
    } catch (err) {
      setError(err.message);
      console.error('Scheduler error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  return { result, loading, error, progress, runScheduler };
};

export const useSchedulerStatus = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchStatus = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/scheduler/status`);
        if (response.ok) {
          const result = await response.json();
          setStatus(result);
        }
      } catch (err) {
        console.error('Status fetch error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 5000); // Poll every 5s
    return () => clearInterval(interval);
  }, []);

  return { status, loading };
};

// ==================== SITES HOOKS ====================

export const useSiteRankings = (filters = {}) => {
  const [rankings, setRankings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchRankings = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        top_n: filters.top_n || 20,
        min_score: filters.min_score || 0,
        ...(filters.zone_id && { zone_id: filters.zone_id })
      });

      const response = await fetch(`${API_BASE}/api/sites/rankings?${params}`);
      if (!response.ok) throw new Error('Failed to fetch site rankings');
      
      const result = await response.json();
      setRankings(result.rankings || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchRankings();
  }, [fetchRankings]);

  return { rankings, loading, error, refetch: fetchRankings };
};

export const useSiteDetail = (wardId) => {
  const [site, setSite] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!wardId) return;

    const fetchSite = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/sites/${wardId}`);
        if (!response.ok) throw new Error('Failed to fetch site detail');
        
        const result = await response.json();
        setSite(result);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchSite();
  }, [wardId]);

  return { site, loading, error };
};

export const useSiteGeoJSON = () => {
  const [geojson, setGeojson] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchGeoJSON = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/sites/geojson`);
        if (!response.ok) throw new Error('Failed to fetch GeoJSON');
        
        const result = await response.json();
        setGeojson(result);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchGeoJSON();
  }, []);

  return { geojson, loading, error };
};

export const useCoverageGaps = () => {
  const [gaps, setGaps] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchGaps = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/sites/coverage-gaps`);
        if (response.ok) {
          const result = await response.json();
          setGaps(result.gaps || []);
        }
      } catch (err) {
        console.error('Coverage gaps fetch error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchGaps();
  }, []);

  return { gaps, loading };
};

// ==================== CARBON HOOKS ====================

export const useCarbonSummary = () => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchSummary = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/carbon/summary`);
        if (!response.ok) throw new Error('Failed to fetch carbon summary');
        
        const result = await response.json();
        setSummary(result);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchSummary();
  }, []);

  return { summary, loading, error };
};

export const useCarbonMonthly = (startMonth, endMonth) => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchMonthly = async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (startMonth) params.append('start_month', startMonth);
        if (endMonth) params.append('end_month', endMonth);

        const response = await fetch(`${API_BASE}/api/carbon/monthly?${params}`);
        if (!response.ok) throw new Error('Failed to fetch monthly data');
        
        const result = await response.json();
        setData(result.monthly_data || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchMonthly();
  }, [startMonth, endMonth]);

  return { data, loading, error };
};

export const useCarbonCertificate = (month) => {
  const [certificate, setCertificate] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchCertificate = useCallback(async () => {
    if (!month) return;

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/carbon/certificate/${month}`);
      if (!response.ok) throw new Error('Failed to fetch certificate');
      
      const result = await response.json();
      setCertificate(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [month]);

  useEffect(() => {
    fetchCertificate();
  }, [fetchCertificate]);

  return { certificate, loading, error, refetch: fetchCertificate };
};

export const useCarbonProjections = () => {
  const [projections, setProjections] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchProjections = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/carbon/projections`);
        if (response.ok) {
          const result = await response.json();
          setProjections(result.projections || []);
        }
      } catch (err) {
        console.error('Projections fetch error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchProjections();
  }, []);

  return { projections, loading };
};

// ==================== ALERTS HOOKS ====================

export const useAlertStream = (onAlert) => {
  const [connected, setConnected] = useState(false);
  const [lastAlert, setLastAlert] = useState(null);
  const [alertCount, setAlertCount] = useState(0);
  const eventSourceRef = useRef(null);

  useEffect(() => {
    const connectStream = () => {
      try {
        const eventSource = new EventSource(`${API_BASE}/api/alerts/stream`);

        eventSource.onopen = () => {
          setConnected(true);
          console.log('✅ Alert stream connected');
        };

        eventSource.onmessage = (event) => {
          try {
            const alert = JSON.parse(event.data);
            setLastAlert(alert);
            setAlertCount(prev => prev + 1);
            if (onAlert) onAlert(alert);
          } catch (err) {
            console.error('Failed to parse alert:', err);
          }
        };

        eventSource.onerror = () => {
          console.warn('Alert stream error, reconnecting...');
          setConnected(false);
          eventSource.close();
          // Reconnect after 3 seconds
          setTimeout(connectStream, 3000);
        };

        eventSourceRef.current = eventSource;
      } catch (err) {
        console.error('Failed to connect alert stream:', err);
        setConnected(false);
      }
    };

    connectStream();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [onAlert]);

  return { connected, lastAlert, alertCount };
};

export const useAlertHistory = (limit = 100) => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/alerts/history?limit=${limit}`);
      if (!response.ok) throw new Error('Failed to fetch alert history');
      
      const result = await response.json();
      setAlerts(result.alerts || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  return { alerts, loading, error, refetch: fetchHistory };
};

export const useFeederStatus = () => {
  const [feeders, setFeeders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  useEffect(() => {
    const fetchStatus = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/alerts/feeders/status`);
        if (!response.ok) throw new Error('Failed to fetch feeder status');
        
        const result = await response.json();
        setFeeders(result.feeders || []);
        setLastUpdated(new Date().toISOString());
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    // Initial fetch
    fetchStatus();

    // Poll every 15 seconds
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  return { feeders, loading, error, lastUpdated };
};

export const useAlertSummary = () => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchSummary = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/alerts/summary`);
        if (response.ok) {
          const result = await response.json();
          setSummary(result);
        }
      } catch (err) {
        console.error('Alert summary fetch error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchSummary();
    const interval = setInterval(fetchSummary, 10000); // Update every 10s
    return () => clearInterval(interval);
  }, []);

  return { summary, loading };
};

// ==================== HEALTH CHECK HOOK ====================

export const useHealthCheck = () => {
  const [health, setHealth] = useState(null);
  const [isHealthy, setIsHealthy] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const checkHealth = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/health`);
        if (response.ok) {
          const result = await response.json();
          setHealth(result);
          setIsHealthy(result.status === 'healthy');
        } else {
          setIsHealthy(false);
        }
      } catch (err) {
        console.error('Health check error:', err);
        setIsHealthy(false);
      } finally {
        setLoading(false);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000); // Check every 30s
    return () => clearInterval(interval);
  }, []);

  return { health, isHealthy, loading };
};

// ==================== SCHEDULER OVERRIDE HOOK ====================

export const useSchedulerOverride = () => {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const sendOverride = useCallback(async (feederId, threshold, action) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/scheduler/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          feeder_id: feederId,
          threshold_pct: threshold,
          action: action
        })
      });

      if (!response.ok) {
        throw new Error(`Override API error: ${response.statusText}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
      console.error('Override error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  return { result, loading, error, sendOverride };
};
