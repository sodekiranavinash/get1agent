import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Auth0ProviderWithNavigate } from './auth/Auth0ProviderWithNavigate.tsx'
import { ViewProvider } from './auth/ViewProvider.tsx'
import { ThemeProvider } from './theme/ThemeProvider.tsx'
import { TooltipProvider } from './components/ui/tooltip.tsx'
import { Toaster } from './components/ui/sonner.tsx'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <TooltipProvider>
          <Auth0ProviderWithNavigate>
            <ViewProvider>
              <App />
              <Toaster />
            </ViewProvider>
          </Auth0ProviderWithNavigate>
        </TooltipProvider>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)
