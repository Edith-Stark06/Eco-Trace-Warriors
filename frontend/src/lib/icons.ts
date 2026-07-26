/**
 * Central icon registry.
 *
 * All Lucide icons used across the app are re-exported from this single module
 * so components import from `@/lib/icons` instead of scattering
 * `lucide-react` imports (and their exact icon names) throughout the codebase.
 * Swapping an icon is then a one-line change here.
 */
import {
  AlertTriangle,
  Bell,
  Check,
  ChevronRight,
  Circle,
  Coins,
  LayoutDashboard,
  Leaf,
  Loader2,
  LogOut,
  type LucideIcon,
  Menu,
  Monitor,
  Moon,
  Package,
  Pencil,
  Plus,
  Recycle,
  Search,
  Settings,
  Shield,
  ShieldCheck,
  Sun,
  Trash2,
  Truck,
  User,
  Users,
} from 'lucide-react';

export type { LucideIcon };

export const icons = {
  brand: Leaf,
  dashboard: LayoutDashboard,
  consumer: User,
  collector: Truck,
  recycler: Recycle,
  government: Shield,
  admin: ShieldCheck,
  settings: Settings,
  users: Users,
  logout: LogOut,
  menu: Menu,
  bell: Bell,
  search: Search,
  chevronRight: ChevronRight,
  spinner: Loader2,
  alert: AlertTriangle,
  check: Check,
  circle: Circle,
  coins: Coins,
  package: Package,
  plus: Plus,
  edit: Pencil,
  trash: Trash2,
  themeLight: Sun,
  themeDark: Moon,
  themeSystem: Monitor,
} satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof icons;
