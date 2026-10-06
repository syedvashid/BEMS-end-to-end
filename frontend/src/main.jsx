import { Component, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './styles/theme.css'
import './styles/base.css'
import App from './App.jsx'
import { ToastProvider } from './components/ui'
import { ActingUserProvider } from './context/ActingUserContext.jsx'
import { FacilityProvider } from './context/FacilityContext.jsx'

console.log('ENV', import.meta.env.MODE, import.meta.env.VITE_DEV_AUTH)

// TEMP debug: shows render errors on screen and logs them. Remove once the white screen is fixed.
class DebugBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('RENDER ERROR:', error, info.componentStack)
  }

  render() {
    return this.state.error ? (
      <pre style={{ padding: 16, whiteSpace: 'pre-wrap' }}>
        {String(this.state.error.stack || this.state.error)}
      </pre>
    ) : (
      this.props.children
    )
  }
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <DebugBoundary>
      <BrowserRouter>
        <ToastProvider>
          <ActingUserProvider>
            <FacilityProvider>
              <App />
            </FacilityProvider>
          </ActingUserProvider>
        </ToastProvider>
      </BrowserRouter>
    </DebugBoundary>
  </StrictMode>,
)