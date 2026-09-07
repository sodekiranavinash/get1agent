import { NavLink } from 'react-router-dom'
import { motion } from 'framer-motion'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useSidebar } from '../components/layout/SidebarProvider'
import { IconButton } from '../components/ui/IconButton'
import {
  sectionOrder,
  sidebarLinks,
  sidebarSections,
} from '../navigation/sidebarLinks'

export function Sidebar() {
  const { collapsed, toggle } = useSidebar()

  return (
    <nav className="flex h-full flex-col scrollbar-thin overflow-y-auto overflow-x-hidden py-4">
      <div className={`mb-2 flex ${collapsed ? 'justify-center px-2' : 'justify-end px-3'}`}>
        <IconButton
          size="sm"
          onClick={toggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" strokeWidth={1.75} />
          ) : (
            <PanelLeftClose className="h-4 w-4" strokeWidth={1.75} />
          )}
        </IconButton>
      </div>

      <div className={`flex flex-1 flex-col gap-1 ${collapsed ? 'px-2' : 'px-3'}`}>
        {sectionOrder.map((sectionKey) => {
          const links = sidebarLinks.filter((link) => link.section === sectionKey)
          if (links.length === 0) return null

          return (
            <div key={sectionKey} className="mb-2">
              {!collapsed ? (
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
                    title={collapsed ? link.label : undefined}
                    className={({ isActive }) =>
                      `group relative mb-0.5 flex items-center rounded-xl text-sm font-medium no-underline transition-all duration-200 ${
                        collapsed ? 'justify-center px-0 py-2.5' : 'gap-3 px-3 py-2.5'
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
                        {!collapsed ? (
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
    </nav>
  )
}
