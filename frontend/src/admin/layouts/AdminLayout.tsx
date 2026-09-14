import { Suspense, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Outlet, useLocation } from 'react-router-dom'
import { AppFooter } from '../../components/layout/AppFooter'
import { TopBar } from '../../components/layout/TopBar'
import { SidebarProvider, useSidebar } from '../../components/layout/SidebarProvider'
import { RouteSkeleton } from '../../components/ui/RouteSkeleton'
import { AdminSidebar } from './AdminSidebar'

/**
 * Admin console shell. Mirrors `MainLayout` (same logo, sidebar, footer and
 * route animation) but renders the admin sidebar and lives under `/admin`.
 */
function RouteGate({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-0 flex-1 flex-col">
          <RouteSkeleton />
        </div>
      }
    >
      {children}
    </Suspense>
  )
}

function AdminLayoutContent() {
  const { effectiveCollapsed } = useSidebar()
  const location = useLocation()

  return (
    <div className="min-h-screen bg-canvas text-foreground">
      <aside
        className={`fixed inset-y-0 left-0 z-20 overflow-hidden border-r border-border bg-surface transition-[width] duration-200 ease-out ${
          effectiveCollapsed ? 'w-[60px]' : 'w-[240px]'
        }`}
      >
        <AdminSidebar />
      </aside>

      <main
        className={`flex min-h-screen flex-col transition-[padding] duration-200 ease-out ${
          effectiveCollapsed ? 'pl-[60px]' : 'pl-[240px]'
        }`}
      >
        <TopBar settingsPath={null} />
        <div className="flex min-h-0 flex-1 flex-col">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.14, ease: 'easeOut' }}
              className="flex min-h-0 flex-1 flex-col"
            >
              <RouteGate>
                <Outlet />
              </RouteGate>
            </motion.div>
          </AnimatePresence>
        </div>
        <AppFooter />
      </main>
    </div>
  )
}

export function AdminLayout() {
  return (
    <SidebarProvider>
      <AdminLayoutContent />
    </SidebarProvider>
  )
}
