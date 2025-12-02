# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

## Dev Password Login (Hidden)

This project hides the email/password login form by default and only shows Discord OAuth. To reveal the hidden dev credential form you must set an environment flag and use a key combo.

### 1. Enable Flag

Create one of these files in `frontend/`:

```text
frontend/.env.local
frontend/.env.development
```

Add:

```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
VITE_ENABLE_PASSWORD_LOGIN=true
```

Restart `npm run dev` after saving (Vite reads env on startup).

### 2. Reveal Form

On the login page press `Ctrl + Alt + D` (Windows/Linux) or `Control + Option + D` (macOS). A subtle hint text appears if the flag is active; the form toggles each time.

### 3. Seed Accounts (Example)

```text
test@kesa.uk    / test1234
admin@stonks.com / admin
```

Never keep these credentials or the flag enabled in production builds.

### 4. Troubleshooting

- Not showing: confirm `VITE_ENABLE_PASSWORD_LOGIN=true` and server restart.
- Key ignored: ensure browser focus (not URL bar), try different tab.
- Console check: temporarily `console.log(import.meta.env.VITE_ENABLE_PASSWORD_LOGIN)` in `Login.tsx`.
- Remove in prod: omit variable or set to `false`.

### 5. Hard Removal (Optional)

For stronger production stripping, wrap the dev block with a build-time constant using `define` in `vite.config.ts` or a feature flag system so dead code elimination can remove it.
