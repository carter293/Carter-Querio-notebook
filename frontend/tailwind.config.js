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
        // Semantic color tokens using CSS variables
        surface: {
          DEFAULT: 'rgb(var(--color-surface) / <alpha-value>)',
          elevated: 'rgb(var(--color-surface-elevated) / <alpha-value>)',
          secondary: 'rgb(var(--color-surface-secondary) / <alpha-value>)',
        },
        primary: {
          DEFAULT: 'rgb(var(--color-primary) / <alpha-value>)',
          hover: 'rgb(var(--color-primary-hover) / <alpha-value>)',
        },
        success: {
          DEFAULT: 'rgb(var(--color-success) / <alpha-value>)',
          hover: 'rgb(var(--color-success-hover) / <alpha-value>)',
        },
        error: {
          DEFAULT: 'rgb(var(--color-error) / <alpha-value>)',
          hover: 'rgb(var(--color-error-hover) / <alpha-value>)',
        },
        warning: {
          DEFAULT: 'rgb(var(--color-warning) / <alpha-value>)',
          hover: 'rgb(var(--color-warning-hover) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--color-secondary) / <alpha-value>)',
          hover: 'rgb(var(--color-secondary-hover) / <alpha-value>)',
        },
        status: {
          idle: 'rgb(var(--color-status-idle) / <alpha-value>)',
          running: 'rgb(var(--color-status-running) / <alpha-value>)',
          success: 'rgb(var(--color-status-success) / <alpha-value>)',
          error: 'rgb(var(--color-status-error) / <alpha-value>)',
          blocked: 'rgb(var(--color-status-blocked) / <alpha-value>)',
        },
        text: {
          primary: 'rgb(var(--color-text-primary) / <alpha-value>)',
          secondary: 'rgb(var(--color-text-secondary) / <alpha-value>)',
          tertiary: 'rgb(var(--color-text-tertiary) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--color-border) / <alpha-value>)',
          focus: 'rgb(var(--color-border-focus) / <alpha-value>)',
        },
        output: {
          DEFAULT: 'rgb(var(--color-bg-output) / <alpha-value>)',
          error: 'rgb(var(--color-bg-error) / <alpha-value>)',
          warning: 'rgb(var(--color-bg-warning) / <alpha-value>)',
          info: 'rgb(var(--color-bg-info) / <alpha-value>)',
        },
        table: {
          header: 'rgb(var(--color-table-header) / <alpha-value>)',
          hover: 'rgb(var(--color-table-hover) / <alpha-value>)',
        },
      },
      animation: {
        'pulse-slow': 'pulse 1.5s infinite',
      },
    },
  },
  plugins: [],
}

