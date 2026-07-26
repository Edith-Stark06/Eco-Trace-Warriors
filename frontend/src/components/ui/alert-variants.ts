import { cva } from 'class-variance-authority';

/**
 * Alert style variants (kept separate from the component so the component file
 * only exports components — satisfies react-refresh/only-export-components).
 */
export const alertVariants = cva(
  'relative w-full rounded-lg border px-4 py-3 text-sm [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-foreground [&>svg~*]:pl-7',
  {
    variants: {
      variant: {
        default: 'bg-background text-foreground',
        destructive:
          'border-destructive/50 text-destructive [&>svg]:text-destructive dark:border-destructive',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);
