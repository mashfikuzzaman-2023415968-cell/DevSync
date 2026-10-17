// ESLint flat config (spec §3, §16.5 step 3): typescript-eslint (type-aware),
// React, hooks, jsx-a11y and the security plugin. Zero warnings allowed.
import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import security from "eslint-plugin-security";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage", "playwright-report", "test-results", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    settings: { react: { version: "18.3" } },
    plugins: { react, "react-hooks": reactHooks, "jsx-a11y": jsxA11y, security },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs["jsx-runtime"].rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.strict.rules,
      ...security.configs.recommended.rules,
      "react/no-danger": "error",
      // False positives on typed Record lookups with union keys (DECISIONS D20); real
      // injection sinks (innerHTML, eval, dynamic RegExp…) stay covered by other rules
      // and scripts/check_forbidden.py.
      "security/detect-object-injection": "off",
      // Card-style labels wrap their text a few elements deep.
      "jsx-a11y/label-has-associated-control": ["error", { depth: 4 }],
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "react/jsx-no-target-blank": "error",
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
      // Motion consistency (spec §13.13): durations and delays come from design/motion.ts.
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "Property[key.name=/^(duration|delay|staggerChildren|delayChildren)$/] > Literal[raw=/^[0-9.]+$/]",
          message: "Use a duration from design/motion.ts instead of a number (spec §13.13).",
        },
        {
          selector: "Literal[value=/(^|\\s|:)(duration|delay)-(\\d|\\[)/]",
          message: "Use duration-fast/base/slow/page instead of numeric Tailwind durations.",
        },
        {
          selector: "TemplateElement[value.raw=/(^|\\s|:)(duration|delay)-(\\d|\\[)/]",
          message: "Use duration-fast/base/slow/page instead of numeric Tailwind durations.",
        },
      ],
    },
  },
  {
    // The motion system itself defines the numbers.
    files: ["src/design/motion.ts"],
    rules: { "no-restricted-syntax": "off" },
  },
  {
    // React Three Fiber elements take Three.js props (position, intensity…).
    files: ["src/components/three/**"],
    rules: { "react/no-unknown-property": "off" },
  },
  {
    // Tests index fixed token tables and read build output from known paths.
    files: ["**/*.test.{ts,tsx}", "tests/**", "e2e/**", "scripts/**"],
    rules: {
      "security/detect-object-injection": "off",
      // Card-style labels wrap their text a few elements deep.
      "jsx-a11y/label-has-associated-control": ["error", { depth: 4 }],
      "security/detect-non-literal-fs-filename": "off",
    },
  },
  {
    files: ["**/*.js", "**/*.mjs", "*.config.{js,ts}"],
    ...tseslint.configs.disableTypeChecked,
  },
);
