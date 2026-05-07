import { useState, useEffect } from 'react';
import { MapPin, Filter, AlertCircle } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts';
import { useSiteRankings, useSiteDetail, useSiteGeoJSON, useCoverageGaps } from '../hooks/useAPI';
import L from 'leaflet';

export default function SiteIntelligencePanel() {
  const [selectedTab, setSelectedTab] = useState('rankings');
  const [filters, setFilters] = useState({ zone_id: '', min_score: 0, top_n: 20 });
  const [selectedSite, setSelectedSite] = useState(null);
  const [mapReady, setMapReady] = useState(false);

  const { rankings, loading: rankingsLoading } = useSiteRankings(filters);
  const { site: siteDetail, loading: detailLoading } = useSiteDetail(selectedSite?.ward_id);
  const { geojson, loading: geoLoading } = useSiteGeoJSON();
  const { gaps, loading: gapsLoading } = useCoverageGaps();

  // Initialize map
  useEffect(() => {
    if (selectedTab === 'map' && geojson && !mapReady) {
      const container = document.getElementById('map-container');
      if (container && container.childNodes.length === 0) {
        const map = L.map(container).setView([13.0827, 77.6054], 12);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '© OpenStreetMap',
          maxZoom: 19
        }).addTo(map);

        // Add GeoJSON markers
        if (geojson.features) {
          geojson.features.forEach((feature) => {
            const { coordinates } = feature.geometry;
            const props = feature.properties;
            L.circleMarker([coordinates[1], coordinates[0]], {
              radius: 8,
              fillColor: '#0EA5E9',
              color: '#FFF',
              weight: 2,
              opacity: 1,
              fillOpacity: 0.8
            })
              .bindPopup(`<b>${props.location_name}</b><br/>Score: ${props.score}`)
              .addTo(map);
          });
        }
        setMapReady(true);
      }
    }
  }, [selectedTab, geojson, mapReady]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-primary/10 rounded-xl">
            <MapPin className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-white">Site Intelligence</h2>
            <p className="text-sm text-gray-400">EVCS placement optimization & GIS analysis</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/10">
        {['rankings', 'map', 'gaps'].map((tab) => (
          <button
            key={tab}
            onClick={() => setSelectedTab(tab)}
            className={`px-4 py-3 text-sm font-semibold transition-colors border-b-2 ${
              selectedTab === tab
                ? 'text-primary border-primary'
                : 'text-gray-400 border-transparent hover:text-gray-300'
            }`}
          >
            {tab === 'rankings' && 'Rankings'}
            {tab === 'map' && 'Map'}
            {tab === 'gaps' && 'Coverage Gaps'}
          </button>
        ))}
      </div>

      {selectedTab === 'rankings' && (
        <>
          {/* Filters */}
          <div className="flex flex-col sm:flex-row gap-4 bg-gray-900/40 p-4 rounded-xl border border-white/5">
            <div className="flex-1">
              <label className="text-xs font-semibold text-gray-400 uppercase mb-2 block">Zone Filter</label>
              <select
                value={filters.zone_id}
                onChange={(e) => setFilters({ ...filters, zone_id: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white text-sm focus:outline-none focus:border-primary"
              >
                <option value="">All Zones</option>
                {['whitefield', 'koramangala', 'yelahanka', 'bommanahalli', 'hebbal', 'indiranagar'].map((zone) => (
                  <option key={zone} value={zone}>{zone.toUpperCase()}</option>
                ))}
              </select>
            </div>

            <div className="flex-1">
              <label className="text-xs font-semibold text-gray-400 uppercase mb-2 block">Min VIDYUT Score: {filters.min_score}</label>
              <input
                type="range"
                min="0"
                max="100"
                value={filters.min_score}
                onChange={(e) => setFilters({ ...filters, min_score: Number(e.target.value) })}
                className="w-full accent-primary"
              />
            </div>
          </div>

          {/* Rankings Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {rankingsLoading ? (
              <div className="col-span-2 text-center py-12">
                <div className="inline-block w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
              </div>
            ) : (
              rankings.map((site) => (
                <div
                  key={site.ward_id}
                  onClick={() => setSelectedSite(site)}
                  className={`bg-gray-900/40 border rounded-xl p-6 cursor-pointer transition-all hover:shadow-lg hover:shadow-primary/20 ${
                    selectedSite?.ward_id === site.ward_id ? 'border-primary' : 'border-white/5'
                  }`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <p className="text-xs font-bold text-primary uppercase">Rank #{site.rank}</p>
                      <p className="text-lg font-bold text-white">{site.location_name}</p>
                      <p className="text-xs text-gray-400">{site.ward_id}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-3xl font-black text-primary">{site.vidyut_score}</p>
                      <p className="text-xs text-gray-400">VIDYUT</p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    {site.factors?.slice(0, 3).map((factor, i) => (
                      <div key={i} className="flex items-center justify-between text-xs">
                        <span className="text-gray-400">{factor.factor_name}</span>
                        <div className="flex items-center gap-2">
                          <div className="w-20 bg-gray-700 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-gradient-to-r from-primary to-blue-600 h-full"
                              style={{ width: `${factor.score}%` }}
                            ></div>
                          </div>
                          <span className="text-white font-semibold w-8 text-right">{factor.score}</span>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 pt-4 border-t border-white/5 text-xs text-gray-400">
                    <p>Grid Upgrade: ₹{site.grid_upgrade_cost_crore?.toFixed(2)}Cr | Year 1: {site.year1_utilization_pct?.toFixed(1)}%</p>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Site Detail Radar */}
          {siteDetail && selectedSite && (
            <div className="bg-gray-900/40 border border-white/5 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-white mb-4">Factor Analysis: {selectedSite.location_name}</h3>
              <ResponsiveContainer width="100%" height={350}>
                <RadarChart data={siteDetail.factors || []}>
                  <PolarGrid stroke="rgba(255,255,255,0.1)" />
                  <PolarAngleAxis dataKey="factor_name" tick={{ fontSize: 12, fill: '#9CA3AF' }} />
                  <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 12, fill: '#9CA3AF' }} />
                  <Radar
                    name="Score"
                    dataKey="score"
                    stroke="#0EA5E9"
                    fill="#0EA5E9"
                    fillOpacity={0.6}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}

      {selectedTab === 'map' && (
        <div className="bg-gray-900/40 border border-white/5 rounded-xl overflow-hidden">
          <div
            id="map-container"
            className="w-full h-[calc(100vh-240px)] min-h-[560px] bg-gray-800"
          ></div>
        </div>
      )}

      {selectedTab === 'gaps' && (
        <div className="space-y-4">
          {gapsLoading ? (
            <div className="text-center py-12">
              <div className="inline-block w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin"></div>
            </div>
          ) : gaps.length > 0 ? (
            gaps.map((gap, i) => (
              <div key={i} className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-6 flex items-start gap-4">
                <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-white">{gap.ward_id} - {gap.location_name}</p>
                  <p className="text-xs text-gray-300 mt-1">EV Density: {gap.ev_density_per_sqkm}  /km² | Nearest EVCS: {gap.distance_to_nearest_km} km away</p>
                  <p className="text-xs text-amber-300 mt-2">Policy Gap: &gt; 3.2 km from EVCS</p>
                </div>
              </div>
            ))
          ) : (
            <p className="text-center text-gray-400 py-12">No coverage gaps detected</p>
          )}
        </div>
      )}
    </div>
  );
}
