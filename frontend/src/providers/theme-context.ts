import { createContext } from 'react';

export type Theme = 'light' | 'dark' | 'system';

/** Resolved theme actually applied to the DOM (never 'system'). */
export type ResolvedTheme = 'light' | 'dark';

export interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
}

export const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export const THEME_STORAGE_KEY = 'ecotrace.theme';
