/**
 * SYNAPSE Frontend Configuration
 */

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8082';

export const config = {
  apiBaseUrl: API_BASE_URL,
  apiVersion: 'v1',
  apiTimeout: 30000, // 30 seconds
  
  // WebSocket/SSE configuration
  enableLiveUpdates: true,
  sseReconnectDelay: 5000, // 5 seconds
  
  // Query configuration
  defaultPageSize: 50,
  maxPageSize: 100,
  
  // Graph visualization
  graphMaxNodes: 500,
  graphMaxEdges: 2500,
} as const;

export default config;
