import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Auth0ProviderWithNavigate } from './auth/Auth0ProviderWithNavigate.tsx'
import { ThemeProvider } from './theme/ThemeProvider.tsx'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <Auth0ProviderWithNavigate>
          <App />
        </Auth0ProviderWithNavigate>
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)
