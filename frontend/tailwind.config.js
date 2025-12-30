/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'selector',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Semantic color tokens using CSS variables with OKLCH
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        card: {
          DEFAULT: 'var(--card)',
          foreground: 'var(--card-foreground)',
        },
        popover: {
          DEFAULT: 'var(--popover)',
          foreground: 'var(--popover-foreground)',
        },
        primary: {
          DEFAULT: 'var(--primary)',
          foreground: 'var(--primary-foreground)',
        },
        secondary: {
          DEFAULT: 'var(--secondary)',
          foreground: 'var(--secondary-foreground)',
        },
        muted: {
          DEFAULT: 'var(--muted)',
          foreground: 'var(--muted-foreground)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          foreground: 'var(--accent-foreground)',
        },
        destructive: {
          DEFAULT: 'var(--destructive)',
          foreground: 'var(--destructive-foreground)',
        },
        success: {
          DEFAULT: 'var(--success)',
          foreground: 'var(--success-foreground)',
        },
        warning: {
          DEFAULT: 'var(--warning)',
          foreground: 'var(--warning-foreground)',
        },
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',

        // Legacy color mappings for compatibility
        surface: {
          DEFAULT: 'var(--card)',
          elevated: 'var(--accent)',
          secondary: 'var(--muted)',
        },
        text: {
          primary: 'var(--foreground)',
          secondary: 'var(--muted-foreground)',
          tertiary: 'var(--muted-foreground)',
        },
        status: {
          idle: 'var(--status-idle)',
          running: 'var(--status-running)',
          success: 'var(--status-success)',
          error: 'var(--status-error)',
          blocked: 'var(--status-blocked)',
        },
        output: {
          DEFAULT: 'var(--bg-output)',
          error: 'var(--bg-error)',
          warning: 'var(--bg-warning)',
          info: 'var(--bg-info)',
        },
        table: {
          header: 'var(--table-header)',
          hover: 'var(--table-hover)',
        },
      },
      animation: {
        'pulse-slow': 'pulse 1.5s infinite',
      },
    },
  },
  plugins: [],
}
