import { Outlet } from 'react-router-dom'
import { Navbar } from './Navbar'
import { Sidebar } from './Sidebar'

export function MainLayout() {
  return (
    <div className="min-h-screen bg-canvas text-foreground">
      <header className="fixed inset-x-0 top-0 z-30 h-16 border-b border-border bg-canvas">
        <Navbar />
      </header>
      <aside className="fixed bottom-0 left-0 top-16 z-20 w-64 border-r border-border bg-canvas">
        <Sidebar />
      </aside>
      <main className="min-h-screen pt-16 pl-64">
        <Outlet />
      </main>
    </div>
  )
}
