/**
 * EcoTrace India — Design System Colors
 * Clean, modern sustainability & technology palette.
 */
export const colors = {
  // Brand - Deep sustainable forest & vibrant clean emerald
  primary: {
    dark: '#0F5132',
    main: '#15803D',
    light: '#22C55E',
    surface: '#F0FDF4',
    border: '#DCFCE7',
  },

  // Tech / Digital Identity / Blockchain Accent
  tech: {
    dark: '#0E7490',
    main: '#0284C7',
    light: '#38BDF8',
    surface: '#F0F9FF',
    border: '#E0F2FE',
  },

  // Forest palette scale
  forest: {
    50: '#F0FDF4',
    100: '#DCFCE7',
    200: '#BBF7D0',
    400: '#4ADE80',
    600: '#16A34A',
    700: '#15803D',
    800: '#166534',
    900: '#0F5132',
  },

  // Emerald palette scale
  emerald: {
    50: '#ECFDF5',
    100: '#D1FAE5',
    600: '#059669',
    700: '#047857',
    800: '#065F46',
  },

  // Slate neutral scale
  slate: {
    50: '#F8FAFC',
    100: '#F1F5F9',
    200: '#E2E8F0',
    300: '#CBD5E1',
    400: '#94A3B8',
    500: '#64748B',
    600: '#475569',
    700: '#334155',
    800: '#1E293B',
    900: '#0F172A',
  },

  // Amber warning scale
  amber: {
    50: '#FFFBEB',
    100: '#FEF3C7',
    700: '#B45309',
    800: '#92400E',
  },

  // Rose error scale
  rose: {
    50: '#FFF1F2',
    100: '#FEE2E2',
    200: '#FECACA',
    700: '#BE123C',
    800: '#9F1239',
  },

  // Neutral Backgrounds & Surfaces
  background: {
    app: '#F8FAFC',
    card: '#FFFFFF',
    subtle: '#F1F5F9',
    muted: '#E2E8F0',
  },

  surface: '#FFFFFF',

  // Text Hierarchy
  text: {
    primary: '#0F172A',
    secondary: '#475569',
    muted: '#94A3B8',
    inverse: '#FFFFFF',
    brand: '#166534',
    accent: '#0369A1',
  },

  // Borders & Dividers
  border: {
    light: '#F1F5F9',
    main: '#E2E8F0',
    focused: '#15803D',
    dark: '#CBD5E1',
  },

  // Status & Feedback Badges
  status: {
    success: {
      bg: '#DCFCE7',
      text: '#166534',
      border: '#BBF7D0',
    },
    info: {
      bg: '#E0F2FE',
      text: '#0369A1',
      border: '#BAE6FD',
    },
    warning: {
      bg: '#FEF3C7',
      text: '#92400E',
      border: '#FDE68A',
    },
    error: {
      bg: '#FEE2E2',
      text: '#991B1B',
      border: '#FECACA',
    },
    neutral: {
      bg: '#F1F5F9',
      text: '#475569',
      border: '#E2E8F0',
    },
  },
};

export type Colors = typeof colors;
