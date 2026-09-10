import { Link, NavLink } from 'react-router-dom'
import { motion } from 'framer-motion'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { SidebarThemeSwitcher } from '../components/layout/SidebarThemeSwitcher'
import { SidebarUserSection } from '../components/layout/SidebarUserSection'
import { useSidebar } from '../components/layout/SidebarProvider'
import { useTheme } from '../theme/ThemeProvider'
import {
  sectionOrder,
  sidebarLinks,
  sidebarSections,
} from '../navigation/sidebarLinks'

export function Sidebar() {
  const { effectiveCollapsed, isCompact, toggle } = useSidebar()
  const { theme } = useTheme()
  const logoSrc = theme === 'light' ? '/white_logo.png' : '/dark_logo.png'

  return (
    <nav className="flex h-full flex-col overflow-hidden">
      <div
        className={`shrink-0 border-b border-border/60 ${
          effectiveCollapsed ? 'px-2 py-3' : 'px-3 py-3.5'
        }`}
      >
        {effectiveCollapsed ? (
          <div className="flex flex-col items-center gap-2">
            <Link
              to="/dashboard"
              title="OneAgent"
              className="block shrink-0 leading-none"
            >
              <img
                src={theme === 'light' ? '/favicon-light.png' : '/favicon-dark.png'}
                alt="OneAgent"
                className="block h-9 w-9 object-cover"
              />
            </Link>
            {!isCompact ? (
              <button
                type="button"
                onClick={toggle}
                aria-label="Expand sidebar"
                title="Expand sidebar"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-subtle transition-colors hover:bg-raised hover:text-foreground"
              >
                <PanelLeftOpen className="h-4 w-4" strokeWidth={1.75} />
              </button>
            ) : null}
          </div>
        ) : (
          <div className="grid grid-cols-[1.75rem_1fr_1.75rem] items-center">
            <span aria-hidden="true" />
            <Link
              to="/dashboard"
              title="OneAgent"
              className="flex justify-center rounded-lg px-1 py-0.5 transition-opacity hover:opacity-90"
            >
              <img
                src={logoSrc}
                alt="OneAgent"
                className="h-[3.5rem] w-full max-w-[13.5rem] object-contain"
              />
            </Link>
            <button
              type="button"
              onClick={toggle}
              aria-label="Collapse sidebar"
              title="Collapse sidebar"
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-subtle transition-colors hover:bg-raised hover:text-muted"
            >
              <PanelLeftClose className="h-4 w-4" strokeWidth={1.75} />
            </button>
          </div>
        )}
      </div>

      <div className="scrollbar-thin flex-1 overflow-y-auto overflow-x-hidden py-3">
        <div className={`flex flex-col gap-1 ${effectiveCollapsed ? 'px-2' : 'px-3'}`}>
          {sectionOrder.map((sectionKey) => {
            const links = sidebarLinks.filter((link) => link.section === sectionKey)
            if (links.length === 0) return null

            return (
              <div key={sectionKey} className="mb-2">
                {!effectiveCollapsed ? (
                  <p className="mb-2 px-3 text-[10px] font-bold tracking-[0.16em] text-subtle uppercase">
                    {sidebarSections[sectionKey]}
                  </p>
                ) : (
                  <div className="mb-2 h-px bg-border" aria-hidden="true" />
                )}

                {links.map((link) => {
                  const Icon = link.icon
                  return (
                    <NavLink
                      key={link.to}
                      to={link.to}
                      end={link.to === '/dashboard'}
                      title={effectiveCollapsed ? (link.tooltip ?? link.label) : undefined}
                      className={({ isActive }) =>
                        `group relative mb-0.5 flex items-center rounded-xl text-sm font-medium no-underline transition-all duration-200 ${
                          effectiveCollapsed ? 'justify-center px-0 py-2.5' : 'gap-3 px-3 py-2.5'
                        } ${
                          isActive
                            ? 'bg-accent-soft text-accent'
                            : 'text-muted hover:bg-raised hover:text-foreground'
                        }`
                      }
                    >
                      {({ isActive }) => (
                        <>
                          {isActive ? (
                            <motion.span
                              layoutId="sidebar-active"
                              className="absolute inset-0 rounded-xl border border-accent/25"
                              transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                            />
                          ) : null}
                          <Icon
                            className={`relative z-10 h-[18px] w-[18px] shrink-0 ${isActive ? 'text-accent' : ''}`}
                            strokeWidth={1.75}
                          />
                          {!effectiveCollapsed ? (
                            <span className="relative z-10 truncate">{link.label}</span>
                          ) : null}
                        </>
                      )}
                    </NavLink>
                  )
                })}
              </div>
            )
          })}
        </div>
      </div>

      <div
        className={`shrink-0 space-y-3 border-t border-border/60 bg-surface/50 py-3 backdrop-blur-sm ${
          effectiveCollapsed ? 'flex flex-col items-center px-2' : 'px-3'
        }`}
      >
        <SidebarThemeSwitcher collapsed={effectiveCollapsed} />
        <SidebarUserSection collapsed={effectiveCollapsed} />
      </div>
    </nav>
  )
}
