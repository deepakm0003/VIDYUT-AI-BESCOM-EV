# VIDYUT AI - Frontend React Application

## 📋 Overview

VIDYUT AI Frontend is a modern React 18 + Vite application providing real-time visualization and control for EV grid optimization. Built with premium animations, dark theme, and responsive design.

## 🎯 Features

- **Demand Forecast**: ML-powered load predictions with confidence bands and SHAP explanations
- **Smart Scheduler**: MILP + RL optimization with real-time progress tracking
- **Site Intelligence**: GIS-based EVCS placement rankings with Leaflet mapping
- **Carbon Credits**: Carbon emissions tracking and revenue monetization analytics
- **Alert Console**: SSE real-time alerts with feeder monitoring and override control

## 🛠 Tech Stack

- **React 18** - UI framework with hooks
- **Vite 4** - Build tool with HMR
- **Tailwind CSS 3** - Utility-first styling
- **Recharts** - Interactive data visualization
- **Leaflet** - Map rendering
- **Framer Motion** - Animations
- **Lucide React** - Icon system

## 📦 Dependencies

```json
{
  "react": "^18.2.0",
  "react-dom": "^18.2.0",
  "recharts": "^2.10.3",
  "leaflet": "^1.9.4",
  "react-leaflet": "^4.2.1",
  "lucide-react": "^0.263.1",
  "framer-motion": "^10.16.4"
}
```

## 🚀 Quick Start

### Prerequisites
- Node.js 16+
- npm or yarn
- Backend running at `http://localhost:8000`

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## 📁 Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── DemandForecast.jsx      # 24-48h load predictions
│   │   ├── SmartScheduler.jsx      # MILP+RL optimization UI
│   │   ├── SiteIntelligence.jsx    # GIS-based site rankings
│   │   ├── CarbonCredits.jsx       # Carbon analytics dashboard
│   │   └── AlertConsole.jsx        # Real-time SSE alerts
│   ├── hooks/
│   │   └── useAPI.js               # 15+ custom hooks for API
│   ├── utils/
│   │   └── formatters.js           # Data formatting utilities
│   ├── App.jsx                     # Main app shell
│   ├── App.css                     # Global animations & layout
│   ├── index.css                   # Tailwind directives
│   └── main.jsx                    # React entry point
├── index.html                      # HTML template
├── vite.config.js                  # Vite configuration
├── tailwind.config.js              # Tailwind theming
├── postcss.config.js               # PostCSS pipeline
├── package.json                    # Dependencies
└── README.md                       # This file
```

## 🎨 Design System

### Color Palette
- Primary: `#0EA5E9` (Sky Blue)
- Dark: `#0F172A` to `#1E293B` (Slate)
- Success: `#10B981` (Emerald)
- Warning: `#F59E0B` (Amber)
- Danger: `#EF4444` (Red)

### Animations
- Fade in: 0.6s ease-out
- Slide in: 0.6s ease-out
- Pulse: 2s infinite
- Glow: 2s infinite with shadow

## 🔌 API Integration

All API calls use custom hooks in `src/hooks/useAPI.js`:

```javascript
// Forecast predictions
const { data, loading, error, refetch } = useForecast(zoneId, horizonHours);

// Scheduler optimization
const { result, loading, progress, runScheduler } = useScheduler();

// Site rankings
const { rankings, loading } = useSiteRankings(filters);

// Real-time alerts (SSE)
const { connected, lastAlert } = useAlertStream(onAlertCallback);

// Feeder status (polling)
const { feeders, lastUpdated } = useFeederStatus();

// Health check
const { isHealthy, loading } = useHealthCheck();
```

### API Base URL
- Development: `http://localhost:8000/api` (with Vite proxy)
- Production: Configure in `.env.production`

## 🎯 Component Details

### DemandForecast
- Zone & horizon selectors
- Load forecast LineChart with confidence bands
- Model weights BarChart (LSTM/XGBoost/Prophet)
- SHAP feature importance visualization
- Peak risk window badge
- Natural language summary

### SmartScheduler
- Zone selection & "Run Optimizer" button
- 4-step progress animation during optimization
- Before/After feeder headroom comparison
- EV sessions assignment table
- Peak reduction badge
- Solve time display

### SiteIntelligence
- **Rankings Tab**: Top 20 EVCS sites with factor scores
- **Map Tab**: Leaflet interactive map with GeoJSON markers
- **Coverage Gaps Tab**: Wards >3km from existing EVCS
- Zone & score filtering
- Radar chart for selected site

### CarbonCredits
- Hero stats: MWh shifted, CO₂ avoided, revenue, months tracked
- Monthly breakdown bar chart
- Revenue projection calculator (1/3/5/10 years)
- BEE certificate generator
- Peer comparison metrics

### AlertConsole
- **Live Alerts Tab**: Real-time SSE alert stream
- **Feeder Status Tab**: 500+ feeders with load % and status
- **Override Control Tab**: Feeder curtailment/restore control
- Live counters: Critical/Warning/Safe/Total
- Threshold sliders and action buttons

## 🛟 Formatting Utilities

Located in `src/utils/formatters.js`:

```javascript
formatTimestamp(isoString)        // "Jan 15, 2:30 PM"
formatCurrency(amountInRupees)    // "₹1.23 Cr"
formatPercent(decimal, decimals)  // "45.6%"
formatNumber(num, decimals)       // "2.4K"
formatPower(mw)                   // "125.4 MW"
formatEnergy(mwh)                 // "50.2 MWh"
formatCO2(tonnes)                 // "12.5 T"
formatCoordinates(lat, lng)       // "12.9716°N, 77.5946°E"
formatDuration(seconds)           // "2h 30m"
getSeverityColors(level)          // {bg, text, border}
formatZoneName(zoneId)            // "Whitefield"
```

## 🎮 Dark Theme

The entire app uses a sophisticated dark theme with:
- Gradient backgrounds
- Subtle borders with transparency
- Animated status indicators
- Hover effects with glow
- Smooth transitions

CSS variables in `App.css`:
```css
--primary: #0EA5E9
--bg-dark: #0F172A
--bg-darker: #020617
--surface: #1E293B
--text-primary: #F1F5F9
--text-secondary: #CBD5E1
--text-muted: #94A3B8
```

## 📱 Responsive Design

- Desktop: Full layout with sidebar
- Tablet (1024px): Narrower sidebar
- Mobile (768px): Bottom navigation bar

Breakpoints:
- `lg`: 1024px
- `md`: 768px
- `sm`: 640px

## 🔄 State Management

Uses React hooks for state:
- `useState` - Component state
- `useEffect` - Side effects & data fetching
- `useCallback` - Memoized callbacks
- `useRef` - Persistent references (maps, event sources)

Custom hooks handle:
- API data fetching
- Loading/error states
- Polling intervals (15s for feeders, 30s for health)
- SSE connections with auto-reconnect

## 🚨 Error Handling

All components include:
- Error boundaries with retry buttons
- Loading skeletons during fetch
- User-friendly error messages
- Fallback UI states

## 📊 Chart Types Used

- **LineChart**: Forecast load over time
- **BarChart**: Model weights, monthly data
- **RadarChart**: Site factor scores (7-factor)

All charts are responsive and use dark theme styling.

## 🔐 Environment Variables

Create `.env` in project root:

```env
VITE_API_BASE=http://localhost:8000/api
VITE_APP_VERSION=1.0.0
```

## 🧪 Development Tips

- HMR enabled - changes reflect instantly
- Vite proxy forwards `/api` to backend
- Network tab shows all API calls
- Console logs API errors

## 📈 Performance

- Code splitting via Vite
- Image optimization
- CSS purging with Tailwind
- Lazy loading for components
- Memoized callbacks to prevent re-renders

## 📚 Additional Resources

- [React 18 Docs](https://react.dev)
- [Vite Docs](https://vitejs.dev)
- [Tailwind CSS](https://tailwindcss.com)
- [Recharts](https://recharts.org)
- [Leaflet](https://leafletjs.com)

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/your-feature`
2. Commit changes: `git commit -m "Add feature"`
3. Push to branch: `git push origin feature/your-feature`
4. Submit pull request

## 📄 License

MIT License - See LICENSE file for details

---

**Version**: 1.0.0  
**Last Updated**: 2026-05-07  
**Built with ❤️ for EV Grid Optimization**
