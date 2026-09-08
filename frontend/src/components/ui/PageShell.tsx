import type { ReactNode } from 'react'
import { motion } from 'framer-motion'

type PageShellProps = {
  children: ReactNode
  className?: string
}

export function PageShell({ children, className = '' }: PageShellProps) {
  return (
    <div className={`relative flex flex-1 flex-col app-mesh-bg ${className}`}>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
        className="relative mx-auto max-w-[1400px] px-6 py-8 lg:px-8 lg:py-10"
      >
        {children}
      </motion.div>
    </div>
  )
}
