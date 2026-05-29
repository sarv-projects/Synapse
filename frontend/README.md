# SYNAPSE Frontend v3.0

Modern React 19 + Vite single-page application for SYNAPSE knowledge graph.

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- npm or yarn

### Installation
```bash
cd frontend
npm install
```

### Development
```bash
npm run dev
```
Visit http://localhost:5173

### Build for Production
```bash
npm run build
```

## 🏗️ Architecture

### Technology Stack
- **Framework**: React 19 with TypeScript
- **Build Tool**: Vite 6 (fastest HMR)
- **Styling**: TailwindCSS 4 (utility-first)
- **State Management**: Zustand (minimal boilerplate)
- **Data Fetching**: TanStack Query v5 (caching, SSE)
- **Graph Visualization**: Sigma.js v3 + Graphology (WebGL-powered)
- **Charts**: Recharts (composable React charts)
- **Icons**: Lucide React (MIT-licensed, tree-shakeable)
- **Routing**: React Router v6

### Project Structure
```
frontend/
├── src/
│   ├── components/
│   │   └── layout.tsx          # Main layout with navigation
│   ├── pages/
│   │   ├── dashboard.tsx       # Real-time dashboard with SSE
│   │   ├── search.tsx          # Full-text + vector search
│   │   ├── ask.tsx             # NL query interface
│   │   ├── graph.tsx           # Interactive graph explorer
│   │   ├── diff.tsx            # What changed view
│   │   ├── leaderboard.tsx      # Top tools/models/papers
│   │   ├── quality.tsx          # System health & metrics
│   │   ├── export.tsx           # Graph export UI
│   │   ├── docs.tsx             # API documentation
│   │   └── about.tsx           # Architecture & info
│   ├── styles/
│   │   └── globals.css          # Global styles + custom CSS
│   └── main.tsx                # App root with routing
├── package.json
├── vite.config.ts
├── tsconfig.json
└── README.md
```

## 📱 Pages & Features

### Dashboard (`/`)
- **Real-time Stats**: Live graph metrics via Server-Sent Events
- **Pipeline Status**: Current ingestion state and health
- **Circuit Breakers**: Source health with visual indicators
- **Activity Charts**: 7-day activity visualization
- **Freshness Metrics**: Data lag indicators

### Search (`/search`)
- **Full-text Search**: Neo4j BM25 search
- **Vector Search**: pgvector semantic similarity
- **Type Filtering**: Filter by entity type
- **Confidence Slider**: Filter by trust level
- **Cursor Pagination**: Efficient large result sets
- **Evidence Links**: Direct source verification

### Ask SYNAPSE (`/ask`)
- **Natural Language**: Query in plain English
- **Streaming Response**: Real-time query processing
- **Query Suggestions**: AI-powered question suggestions
- **Cypher Display**: Generated query transparency
- **Step-by-step Reasoning**: Evidence trail
- **Error Handling**: Clear error messages and suggestions

### Graph Explorer (`/graph/:entity`)
- **Interactive Visualization**: Sigma.js WebGL rendering
- **Node Expansion**: Click to explore neighborhoods
- **Search Highlight**: In-graph search with fade
- **Export Visible**: Download current viewport
- **Node Details**: Properties panel with expansion
- **Trust Level Colors**: Visual confidence indicators

### Additional Pages
- **What Changed** (`/diff`) - Temporal diff with animations
- **Leaderboards** (`/leaderboard`) - Top tools, models, papers
- **Quality** (`/quality`) - System health, eval metrics
- **Export** (`/export`) - Multi-format graph export
- **API Docs** (`/docs`) - Auto-generated Swagger UI
- **About** (`/about`) - Architecture and setup guide

## 🎨 Design System

### Color Palette
- **Primary**: Indigo (`#4f46e5`)
- **Success**: Green (`#10b981`)
- **Warning**: Yellow (`#f59e0b`)
- **Error**: Red (`#ef4444`)
- **Dark Mode**: Full support with TailwindCSS

### Graph Visualization
- **Node Colors**: By entity type (Paper=indigo, Model=teal, Tool=amber, Technique=navy)
- **Edge Colors**: By verification status (verified=teal, weak=amber, unverified=gray, disputed=red)
- **Node Sizing**: Proportional to GitHub stars/HF downloads
- **Interactions**: Hover, click, zoom, pan

## 🔧 Configuration

### Environment Variables
```bash
# API endpoint
VITE_API_URL=http://localhost:8000

# Development mode
VITE_DEV_MODE=true
```

### API Integration
The frontend expects the SYNAPSE v3.0 API with these endpoints:

- `GET /api/v1/health` - Dashboard stats
- `GET /api/v1/search` - Search with cursor pagination
- `POST /api/v1/query` - Natural language queries
- `GET /api/v1/technique/{name}/ecosystem` - Graph data
- `GET /api/v1/export` - Multi-format export
- `GET /api/v1/whats-new` - Recent changes
- Server-Sent Events for real-time updates

## 🚀 Deployment

### DigitalOcean App Platform
```bash
# Build
npm run build

# Deploy to DigitalOcean
# (Configure via App Platform control panel)
# Static site hosting with CDN included
```

### Environment-Specific Builds
```bash
# Development
npm run dev

# Production
npm run build

# Preview production build
npm run preview
```

## 📊 Performance Features

### Optimizations
- **Code Splitting**: Manual chunks for optimal loading
- **Tree Shaking**: Dead code elimination
- **Lazy Loading**: Route-based code splitting
- **Caching**: TanStack Query with 5-minute stale time
- **Bundle Analysis**: Built-in bundle analyzer

### Monitoring
- **Error Boundaries**: Graceful error handling
- **Performance Metrics**: Core Web Vitals tracking
- **API Error Handling**: Retry logic with user feedback

## 🛠️ Development

### Available Scripts
```bash
npm run dev          # Development server
npm run build        # Production build
npm run preview      # Preview build
npm run lint         # ESLint checking
npm run lint:fix     # Auto-fix linting issues
```

### Code Quality
- **TypeScript**: Full type safety
- **ESLint**: Consistent code style
- **Prettier**: Code formatting (configured)
- **Husky**: Pre-commit hooks (recommended)

## 🔌 API Integration Examples

### Fetching Dashboard Stats
```typescript
const { data } = useQuery({
  queryKey: ['dashboard-stats'],
  queryFn: async () => {
    const response = await fetch('/api/v1/health')
    return response.json()
  },
  refetchInterval: 30000, // 30 seconds
})
```

### Search with Pagination
```typescript
const { data, fetchNextPage, hasNextPage } = useQuery({
  queryKey: ['search', query, type, cursor],
  queryFn: ({ pageParam }) => {
    const params = new URLSearchParams({
      q: query,
      type: type,
      cursor: pageParam
    })
    return fetch(`/api/v1/search?${params}`).then(r => r.json())
  }
})
```

## 🎯 Next Steps

1. **Environment Setup**: Configure API endpoints
2. **Development**: `npm run dev` to start building
3. **Testing**: Verify all API integrations
4. **Deployment**: Build and deploy to DigitalOcean
5. **Monitoring**: Set up error tracking and analytics

## 📱 Responsive Design

- **Mobile-First**: Progressive enhancement
- **Touch-Friendly**: Large tap targets
- **Adaptive Layout**: Collapsible navigation
- **Performance**: Optimized for mobile networks

## 🔐 Security Features

- **CORS Handling**: Proper cross-origin requests
- **Content Security**: XSS prevention
- **API Key Support**: Secure authentication
- **Input Validation**: Client-side sanitization

## 🎨 Customization

### Theming
- **Dark Mode**: Full dark theme support
- **Color Variables**: CSS custom properties
- **Component Variants**: Consistent design system

### Branding
- **Logo**: Replace SYNAPSE branding
- **Colors**: Customize primary/accent colors
- **Typography**: Font family adjustments

---

**Ready for development!** This frontend provides a complete, modern interface for the SYNAPSE v3.0 knowledge graph platform.
