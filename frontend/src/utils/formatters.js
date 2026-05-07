/**
 * Utility functions for formatting data across the VIDYUT AI frontend
 */

/**
 * Format timestamp to readable date+time string
 * @param {string|Date} timestamp - ISO timestamp or Date object
 * @returns {string} Formatted time string (e.g., "Jan 15, 2:30 PM")
 */
export const formatTimestamp = (timestamp) => {
  if (!timestamp) return 'N/A';
  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true
  });
};

/**
 * Format currency in Indian Rupees
 * @param {number} amount - Amount in rupees
 * @returns {string} Formatted currency (e.g., "₹1,234.56 Cr")
 */
export const formatCurrency = (amount) => {
  if (!amount) return '₹0';
  
  if (amount >= 1e7) {
    return `₹${(amount / 1e7).toFixed(2)} Cr`;
  } else if (amount >= 1e5) {
    return `₹${(amount / 1e5).toFixed(2)} L`;
  } else if (amount >= 1e3) {
    return `₹${(amount / 1e3).toFixed(2)} K`;
  }
  return `₹${amount.toFixed(2)}`;
};

/**
 * Format percentage with specified decimal places
 * @param {number} value - Decimal value (e.g., 0.456 for 45.6%)
 * @param {number} decimals - Decimal places to show (default: 1)
 * @returns {string} Formatted percentage (e.g., "45.6%")
 */
export const formatPercent = (value, decimals = 1) => {
  if (value === null || value === undefined) return 'N/A';
  return `${(value * 100).toFixed(decimals)}%`;
};

/**
 * Format large numbers with abbreviation
 * @param {number} num - Number to format
 * @param {number} decimals - Decimal places (default: 1)
 * @returns {string} Formatted number (e.g., "2.4K", "1.2M")
 */
export const formatNumber = (num, decimals = 1) => {
  if (!num) return '0';
  
  if (num >= 1e9) {
    return `${(num / 1e9).toFixed(decimals)}B`;
  } else if (num >= 1e6) {
    return `${(num / 1e6).toFixed(decimals)}M`;
  } else if (num >= 1e3) {
    return `${(num / 1e3).toFixed(decimals)}K`;
  }
  return num.toFixed(decimals);
};

/**
 * Format power in MW/kW
 * @param {number} powerMw - Power in megawatts
 * @returns {string} Formatted power (e.g., "125.4 MW" or "12,540 kW")
 */
export const formatPower = (powerMw) => {
  if (!powerMw) return '0 MW';
  
  if (powerMw >= 1) {
    return `${powerMw.toFixed(1)} MW`;
  }
  return `${(powerMw * 1000).toFixed(0)} kW`;
};

/**
 * Format energy in MWh/kWh
 * @param {number} energyMwh - Energy in megawatt-hours
 * @returns {string} Formatted energy
 */
export const formatEnergy = (energyMwh) => {
  if (!energyMwh) return '0 MWh';
  
  if (energyMwh >= 1) {
    return `${energyMwh.toFixed(2)} MWh`;
  }
  return `${(energyMwh * 1000).toFixed(0)} kWh`;
};

/**
 * Format CO2 emissions in tonnes
 * @param {number} tonnes - Emissions in metric tonnes
 * @returns {string} Formatted emissions (e.g., "12.5 T" or "12,543 kg")
 */
export const formatCO2 = (tonnes) => {
  if (!tonnes) return '0 T';
  
  if (tonnes >= 1) {
    return `${tonnes.toFixed(1)} T`;
  }
  return `${(tonnes * 1000).toFixed(0)} kg`;
};

/**
 * Format geographic coordinates
 * @param {number} lat - Latitude
 * @param {number} lng - Longitude
 * @returns {string} Formatted coordinates (e.g., "12.9716°N, 77.5946°E")
 */
export const formatCoordinates = (lat, lng) => {
  if (!lat || !lng) return 'N/A';
  return `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lng).toFixed(4)}°${lng >= 0 ? 'E' : 'W'}`;
};

/**
 * Format time duration to human-readable string
 * @param {number} seconds - Duration in seconds
 * @returns {string} Formatted duration (e.g., "2h 30m", "45s")
 */
export const formatDuration = (seconds) => {
  if (!seconds) return '0s';
  
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  
  if (hours > 0) {
    return `${hours}h ${mins}m`;
  } else if (mins > 0) {
    return `${mins}m ${secs}s`;
  }
  return `${secs}s`;
};

/**
 * Get severity badge color classes
 * @param {string} severity - Severity level (CRITICAL, HIGH, MEDIUM, LOW)
 * @returns {object} Tailwind color classes {bg, text, border}
 */
export const getSeverityColors = (severity) => {
  const colors = {
    'CRITICAL': { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/50' },
    'HIGH': { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500/50' },
    'MEDIUM': { bg: 'bg-yellow-500/20', text: 'text-yellow-400', border: 'border-yellow-500/50' },
    'LOW': { bg: 'bg-green-500/20', text: 'text-green-400', border: 'border-green-500/50' }
  };
  return colors[severity] || colors['LOW'];
};

/**
 * Format zone name to title case with proper spacing
 * @param {string} zoneId - Zone identifier (e.g., "whitefield" -> "Whitefield")
 * @returns {string} Formatted zone name
 */
export const formatZoneName = (zoneId) => {
  if (!zoneId) return 'Unknown';
  return zoneId
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
};
