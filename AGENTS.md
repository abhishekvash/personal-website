## Clean Diagnostics

Run these commands from the workspace root:

- Type check: `pnpm exec tsc --noEmit`
- Lint: `pnpm run lint`
- Format check (read-only): `pnpm run check`
- Apply formatting and ESLint fixes: `pnpm run format`
- Build: `pnpm run build`

When cleaning diagnostics, fix safe issues and rerun the affected checks. Ask before fixes that could change application behavior or user experience. Run the build after type, lint, and formatting checks pass, and report any remaining failures or blockers. Do not add tests unless requested.
