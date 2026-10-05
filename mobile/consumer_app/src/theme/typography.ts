import { TextStyle } from 'react-native';

const sizes = {
  hero: 32,
  xxl: 28,
  xl: 24,
  title: 24,
  lg: 20,
  subtitle: 18,
  base: 16,
  bodyLarge: 16,
  sm: 14,
  body: 14,
  xs: 12,
  caption: 12,
  xxs: 10,
  micro: 10,
} as const;

const weights = {
  regular: '400' as TextStyle['fontWeight'],
  normal: '400' as TextStyle['fontWeight'],
  medium: '500' as TextStyle['fontWeight'],
  semibold: '600' as TextStyle['fontWeight'],
  bold: '700' as TextStyle['fontWeight'],
  heavy: '800' as TextStyle['fontWeight'],
} as const;

const lineHeights = {
  hero: 38,
  title: 30,
  subtitle: 24,
  bodyLarge: 22,
  body: 20,
  caption: 16,
  micro: 14,
} as const;

export const typography = {
  sizes,
  weights,
  lineHeights,
  size: sizes,
  weight: weights,
} as const;
