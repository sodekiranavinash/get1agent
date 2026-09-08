import { AnimatePresence, motion } from 'framer-motion'
import { Outlet, useLocation } from 'react-router-dom'
import { AppFooter } from '../components/layout/AppFooter'
import { SidebarProvider, useSidebar } from '../components/layout/SidebarProvider'
import { Sidebar } from './Sidebar'

function MainLayoutContent() {
  const { collapsed } = useSidebar()
  const location = useLocation()

  return (
    <div className="min-h-screen bg-canvas text-foreground">
      <aside
        className={`fixed inset-y-0 left-0 z-20 border-r border-border bg-surface/95 backdrop-blur-xl transition-[width] duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] ${
          collapsed ? 'w-[72px]' : 'w-64'
        }`}
      >
        <Sidebar />
      </aside>

      <main
        className={`flex min-h-screen flex-col transition-[padding] duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] ${
          collapsed ? 'pl-[72px]' : 'pl-64'
        }`}
      >
        <div className="flex min-h-0 flex-1 flex-col">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
              className="flex min-h-0 flex-1 flex-col"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </div>
        <AppFooter />
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
