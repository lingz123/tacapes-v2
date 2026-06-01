import type { Config } from 'tailwindcss';
import tailwindcssAnimate from 'tailwindcss-animate';

// Tokens are defined as CSS variables in src/styles/tokens.css so they can
// be overridden at runtime (dark mode toggle in Sprint 2). Tailwind reads
// those vars through the colors map below — keep the two in sync.
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: {
      center: true,
      padding: '1.5rem',
      screens: { '2xl': '1280px' },
    },
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        // Semantic accent tokens used by ConvictionBadge, AlignmentBadge,
        // RatingBadge, PnlPill, weak-spot icons.
        good: { DEFAULT: 'hsl(var(--good))', bg: 'hsl(var(--good-bg))' },
        warn: { DEFAULT: 'hsl(var(--warn))', bg: 'hsl(var(--warn-bg))' },
        bad:  { DEFAULT: 'hsl(var(--bad))',  bg: 'hsl(var(--bad-bg))'  },
        info: { DEFAULT: 'hsl(var(--info))', bg: 'hsl(var(--info-bg))' },
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        DEFAULT: 'var(--radius)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        DEFAULT: 'var(--shadow)',
      },
      fontFamily: {
        sans: ['"Inter Variable"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono Variable"', 'JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        '2xs': ['11px', '1.4'],
        xs: ['12px', '1.4'],
        sm: ['13px', '1.5'],
        base: ['14px', '1.5'],
        md: ['16px', '1.5'],
        lg: ['18px', '1.4'],
        xl: ['22px', '1.3'],
        '2xl': ['28px', '1.2'],
        '3xl': ['36px', '1.15'],
      },
      keyframes: {
        // Shadcn accordion expects these so the Radix data-state transitions
        // animate without us hand-rolling CSS.
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.18s ease-out',
        'accordion-up': 'accordion-up 0.18s ease-out',
      },
    },
  },
  plugins: [tailwindcssAnimate],
} satisfies Config;
