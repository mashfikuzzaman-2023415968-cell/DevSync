# End-to-end tests

Playwright tests live in `frontend/e2e/` (DECISIONS.md D11) so they share the frontend's
`node_modules`. The gate runs them in the pinned Playwright image against Nginx.
