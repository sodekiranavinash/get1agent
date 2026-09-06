import { Link } from 'react-router-dom'
import { UserMenu } from '../components/UserMenu'
import { ThemeToggle } from '../theme/ThemeToggle'
import { useTheme } from '../theme/ThemeProvider'

export function Navbar() {
  const { theme } = useTheme()
  const logoSrc = theme === 'light' ? '/white_logo.png' : '/dark_logo.png'

  return (
    <div className="flex h-full w-full items-center justify-between gap-4 px-4">
      <Link to="/" className="flex h-full shrink-0 items-center">
        <img
          src={logoSrc}
          alt="OneAgent"
          className="h-14 w-[14rem] object-contain object-left"
        />
      </Link>
      <div className="flex items-center gap-3">
        <ThemeToggle />
        <UserMenu />
      </div>
    </div>
  )
}
