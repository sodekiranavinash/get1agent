import { AnimatePresence, motion } from 'framer-motion'
import { Outlet, useLocation } from 'react-router-dom'
import { SidebarProvider, useSidebar } from '../components/layout/SidebarProvider'
import { Navbar } from './Navbar'
import { Sidebar } from './Sidebar'

function MainLayoutContent() {
  const { collapsed } = useSidebar()
  const location = useLocation()

  return (
    <div className="min-h-screen bg-canvas text-foreground">
      <header className="fixed inset-x-0 top-0 z-30 h-16 glass-panel border-b border-border">
        <Navbar />
      </header>

      <aside
        className={`fixed bottom-0 left-0 top-16 z-20 border-r border-border bg-surface/95 backdrop-blur-xl transition-[width] duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] ${
          collapsed ? 'w-[72px]' : 'w-64'
        }`}
      >
        <Sidebar />
      </aside>

      <main
        className={`min-h-screen bg-canvas pt-16 transition-[padding] duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] ${
          collapsed ? 'pl-[72px]' : 'pl-64'
        }`}
      >
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  )
}

export function MainLayout() {
  return (
    <SidebarProvider>
      <MainLayoutContent />
    </SidebarProvider>
  )
}
