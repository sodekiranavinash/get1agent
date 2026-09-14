import { useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import {
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import { useSidebar } from '../components/layout/SidebarProvider'
import { Skeleton } from '../components/ui/Skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '../components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu'
import { useTheme } from '../theme/ThemeProvider'
import {
  sectionOrder as defaultSectionOrder,
  sidebarLinks as defaultLinks,
  sidebarSections as defaultSections,
  type SidebarChild,
  type SidebarLink,
} from '../navigation/sidebarLinks'

type SidebarProps = {
  links?: SidebarLink[]
  sections?: Record<string, string>
  order?: string[]
  homePath?: string
  /** Renders placeholder rows for dynamic links (e.g. admin MCP servers). */
  loading?: boolean
}

const SECTION_STORAGE_KEY = 'sidebar-closed-sections'

function readClosedSections(): string[] {
  try {
    const raw = localStorage.getItem(SECTION_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function isPathActive(pathname: string, to: string, end: boolean): boolean {
  if (end) return pathname === to
  return pathname === to || pathname.startsWith(`${to}/`)
}

function NavRowSkeleton() {
  return (
    <div className="flex h-7 items-center gap-2 rounded-lg px-2">
      <Skeleton className="size-4 shrink-0 rounded-md" />
      <Skeleton className="h-3 flex-1 rounded" />
    </div>
  )
}

function NavIconSkeleton() {
  return <Skeleton className="size-8 shrink-0 rounded-lg" />
}

export function Sidebar({
  links = defaultLinks,
  sections = defaultSections,
  order = defaultSectionOrder,
  homePath = '/dashboard',
  loading = false,
}: SidebarProps = {}) {
  const { effectiveCollapsed, isCompact, toggle } = useSidebar()
  const { theme } = useTheme()
  const location = useLocation()
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})
  const [closedSections, setClosedSections] = useState<string[]>(readClosedSections)
  const collapsed = effectiveCollapsed
  const logoSrc = theme === 'light' ? '/white_logo.png' : '/dark_logo.png'

  const isRoot = (to: string) => to === homePath || to === '/admin/mcp-tools'
  const isLinkActive = (to: string) =>
    isPathActive(location.pathname, to, isRoot(to))
  const isChildActive = (children: SidebarChild[] = []) =>
    children.some((child) => isPathActive(location.pathname, child.to, false))

  // Item chrome shared by every nav row.
  const itemBase =
    'group/menu-button relative flex w-full min-w-0 items-center rounded-lg outline-none transition-[color,background-color,border-color,box-shadow] duration-150'
  const itemIdle = 'text-muted hover:bg-raised hover:text-foreground'
  const itemActive = 'bg-accent-soft text-accent'
  const iconBase = 'shrink-0 transition-opacity'
  const iconIdle = 'text-subtle opacity-60 group-hover/menu-button:opacity-100'
  const iconActive = 'text-accent opacity-100'

  const toggleSection = (key: string) => {
    setClosedSections((current) => {
      const next = current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key]
      try {
        localStorage.setItem(SECTION_STORAGE_KEY, JSON.stringify(next))
      } catch {
        /* ignore */
      }
      return next
    })
  }

  const renderCollapsedItem = (link: SidebarLink) => {
    const Icon = link.icon
    const active = isLinkActive(link.to)
    return (
      <Tooltip key={link.to}>
        <TooltipTrigger asChild>
          <NavLink
            to={link.to}
            end={isRoot(link.to)}
            aria-label={link.tooltip ?? link.label}
            className={`relative flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors duration-150 ${
              active ? itemActive : itemIdle
            }`}
          >
            <Icon
              className={`size-[18px] ${active ? 'text-accent' : ''}`}
              strokeWidth={1.75}
            />
            {link.badge ? (
              <span className="absolute top-1.5 right-1.5 size-1.5 rounded-full bg-accent" />
            ) : null}
          </NavLink>
        </TooltipTrigger>
        <TooltipContent side="right">{link.tooltip ?? link.label}</TooltipContent>
      </Tooltip>
    )
  }

  const renderCollapsedGroup = (link: SidebarLink) => {
    const Icon = link.icon
    const children = link.children ?? []
    const active = isChildActive(children)
    return (
      <DropdownMenu key={link.to}>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label={link.label}
                className={`relative flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors duration-150 ${
                  active ? itemActive : itemIdle
                }`}
              >
                <Icon
                  className={`size-[18px] ${active ? 'text-accent' : ''}`}
                  strokeWidth={1.75}
                />
              </button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="right">{link.label}</TooltipContent>
        </Tooltip>
        <DropdownMenuContent side="right" align="start" className="w-56">
          <DropdownMenuLabel>{link.label}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {children.map((child) => {
            const ChildIcon = child.icon
            const childIsActive = isPathActive(location.pathname, child.to, false)
            return (
              <DropdownMenuItem key={child.to} asChild>
                <NavLink
                  to={child.to}
                  className={`text-[13px] ${childIsActive ? 'font-medium text-accent' : ''}`}
                >
                  {ChildIcon ? (
                    <ChildIcon className="size-4 opacity-70" strokeWidth={1.75} />
                  ) : (
                    <span className="size-1.5 rounded-full bg-subtle" />
                  )}
                  {child.label}
                </NavLink>
              </DropdownMenuItem>
            )
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    )
  }

  const renderExpandedLink = (link: SidebarLink) => {
    const Icon = link.icon
    const active = isLinkActive(link.to)
    return (
      <NavLink
        key={link.to}
        to={link.to}
        end={isRoot(link.to)}
        className={`${itemBase} h-8 gap-2.5 px-3 text-[13px] font-medium no-underline ${
          active ? itemActive : itemIdle
        }`}
      >
        <Icon
          className={`${iconBase} size-4 ${active ? iconActive : iconIdle}`}
          strokeWidth={1.75}
        />
        <span className="min-w-0 flex-1 truncate">{link.label}</span>
        {link.badge ? (
          <span className="shrink-0 rounded-full border border-dashed border-border px-1.5 py-0.5 text-[10px] leading-none font-medium tabular-nums text-muted">
            {link.badge}
          </span>
        ) : null}
      </NavLink>
    )
  }

  const renderExpandedGroup = (link: SidebarLink) => {
    const Icon = link.icon
    const children = link.children ?? []
    const childActive = isChildActive(children)
    const isLoading = loading && children.length === 0
    const groupOpen =
      openGroups[link.to] ?? (childActive || children.length > 0 || isLoading)

    return (
      <div key={link.to} className="mb-0.5">
        <button
          type="button"
          onClick={() =>
            setOpenGroups((current) => ({ ...current, [link.to]: !groupOpen }))
          }
          aria-expanded={groupOpen}
          className={`${itemBase} h-8 gap-2.5 px-3 text-[13px] font-medium hover:shadow-control ${
            childActive ? 'text-foreground' : itemIdle
          }`}
        >
          <Icon
            className={`${iconBase} size-4 ${
              childActive ? iconActive : iconIdle
            }`}
            strokeWidth={1.75}
          />
          <span className="min-w-0 flex-1 truncate text-left">{link.label}</span>
          {link.badge ? (
            <span className="shrink-0 rounded-full border border-dashed border-border px-1.5 py-0.5 text-[10px] leading-none font-medium tabular-nums text-muted">
              {link.badge}
            </span>
          ) : null}
          <ChevronDown
            className={`size-3 shrink-0 opacity-40 transition-[transform,opacity] duration-200 group-hover/menu-button:opacity-100 ${
              groupOpen ? '' : '-rotate-90'
            }`}
            strokeWidth={2}
          />
        </button>

        {/* CSS grid-rows collapse — same technique Cloudflare uses. */}
        <div
          className={`grid transition-[grid-template-rows] duration-200 ease-out ${
            groupOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
          }`}
        >
          <div className="overflow-hidden">
            <div className="mt-0.5 mb-1 ml-[21px] flex flex-col gap-0.5 border-l border-border pl-2.5">
              {isLoading
                ? [0, 1, 2].map((index) => <NavRowSkeleton key={index} />)
                : children.map((child) => {
                    const ChildIcon = child.icon
                    const childIsActive = isPathActive(
                      location.pathname,
                      child.to,
                      false,
                    )
                    return (
                      <NavLink
                        key={child.to}
                        to={child.to}
                        end
                        className={`flex h-7 items-center gap-2 rounded-lg px-2 text-[12px] font-medium no-underline transition-colors duration-150 ${
                          childIsActive
                            ? 'bg-accent-soft text-accent'
                            : 'text-muted hover:bg-raised hover:text-foreground'
                        }`}
                      >
                        {ChildIcon ? (
                          <ChildIcon
                            className="size-4 shrink-0 opacity-70"
                            strokeWidth={1.75}
                          />
                        ) : null}
                        <span className="truncate">{child.label}</span>
                      </NavLink>
                    )
                  })}
            </div>
          </div>
        </div>
      </div>
    )
  }

  const visibleSections = order.filter((key) =>
    links.some((link) => link.section === key),
  )

  return (
    <nav className="flex h-full min-h-0 flex-col">
      <div
        className={`relative flex shrink-0 border-b border-border ${
          collapsed
            ? 'flex-col items-center gap-1.5 py-2'
            : 'h-20 items-center justify-center px-3'
        }`}
      >
        <Link
          to={homePath}
          title="OneAgent"
          className="flex items-center justify-center rounded-lg transition-opacity hover:opacity-90"
        >
          {collapsed ? (
            <img
              src={theme === 'light' ? '/favicon-light.png' : '/favicon-dark.png'}
              alt="OneAgent"
              className="h-10 w-10 object-contain"
            />
          ) : (
            <img
              src={logoSrc}
              alt="OneAgent"
              className="h-12 w-auto max-w-[13.5rem] object-contain"
            />
          )}
        </Link>
        {!collapsed && !isCompact ? (
          <button
            type="button"
            onClick={toggle}
            aria-label="Collapse sidebar"
            title="Collapse sidebar"
            className="absolute right-2 inline-flex size-8 items-center justify-center rounded-lg text-subtle transition-colors duration-150 hover:bg-raised hover:text-foreground"
          >
            <PanelLeftClose className="size-[18px]" strokeWidth={1.75} />
          </button>
        ) : null}
        {collapsed && !isCompact ? (
          <button
            type="button"
            onClick={toggle}
            aria-label="Expand sidebar"
            title="Expand sidebar"
            className="inline-flex size-8 items-center justify-center rounded-lg text-subtle transition-colors duration-150 hover:bg-raised hover:text-foreground"
          >
            <PanelLeftOpen className="size-[18px]" strokeWidth={1.75} />
          </button>
        ) : null}
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col">
        <div
          className={`scrollbar-thin flex min-h-0 flex-1 flex-col overflow-x-hidden overflow-y-auto overscroll-contain pt-2 pb-6 ${
            collapsed ? 'items-center gap-1 px-2' : 'gap-0.5 px-2'
          }`}
        >
          {visibleSections.map((sectionKey, sectionIndex) => {
            const sectionLinks = links.filter((link) => link.section === sectionKey)
            const hasLabel = Boolean(sections[sectionKey])
            const sectionClosed =
              !collapsed && hasLabel && closedSections.includes(sectionKey)

            if (collapsed) {
              return (
                <div
                  key={sectionKey}
                  className="flex w-full flex-col items-center gap-1"
                >
                  {sectionIndex > 0 ? (
                    <span className="my-1 h-px w-7 bg-border" aria-hidden="true" />
                  ) : null}
                  {sectionLinks.map((link) =>
                    loading && !link.children?.length ? (
                      <NavIconSkeleton key={link.to} />
                    ) : link.children?.length ? (
                      renderCollapsedGroup(link)
                    ) : (
                      renderCollapsedItem(link)
                    ),
                  )}
                </div>
              )
            }

            const sectionActive = sectionLinks.some(
              (link) => isLinkActive(link.to) || isChildActive(link.children),
            )

            return (
              <div key={sectionKey} className={hasLabel ? 'mt-2' : ''}>
                {hasLabel ? (
                  <button
                    type="button"
                    onClick={() => toggleSection(sectionKey)}
                    aria-expanded={!sectionClosed}
                    className="flex h-7 w-full items-center gap-2 rounded-lg px-2 text-[11px] font-semibold tracking-[0.08em] uppercase transition-[background-color,box-shadow] duration-150 hover:bg-raised/60 hover:shadow-control"
                  >
                    <span
                      className={`flex-1 text-left ${
                        sectionActive ? 'text-foreground' : 'text-muted'
                      }`}
                    >
                      {sections[sectionKey]}
                    </span>
                    <ChevronDown
                      className={`size-3.5 shrink-0 text-subtle opacity-40 transition-transform duration-200 ${
                        sectionClosed ? '-rotate-90' : ''
                      }`}
                      strokeWidth={2}
                    />
                  </button>
                ) : null}
                <div
                  className={`grid transition-[grid-template-rows] duration-200 ease-out ${
                    sectionClosed ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]'
                  }`}
                >
                  <div className="overflow-hidden">
                    <div
                      className={`relative flex flex-col gap-0.5 ${
                        hasLabel ? 'pl-3' : ''
                      }`}
                    >
                      {hasLabel ? (
                        <span
                          className="absolute inset-y-0.5 left-2 w-px bg-border"
                          aria-hidden="true"
                        />
                      ) : null}
                      {sectionLinks.map((link) =>
                        link.children?.length || loading
                          ? renderExpandedGroup(link)
                          : renderExpandedLink(link),
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        <div
          className="pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-surface to-transparent"
          aria-hidden="true"
        />
      </div>
    </nav>
  )
}
