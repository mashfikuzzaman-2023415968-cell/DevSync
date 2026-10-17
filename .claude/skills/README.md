# Project skills (spec §0.4)

Installed at project level so every team member's Claude Code uses the same versions.
Reviewed 2026-10-17 by Mashfikuzzaman Taeen with Claude Code: every `SKILL.md` was read; the
skills are Markdown only (no scripts), download nothing at runtime, need no API keys and do
not change security settings. Update only deliberately, repeating the review and recording
the new commit in `DECISIONS.md`.

| Skill | Source | Commit | Purpose |
|---|---|---|---|
| `frontend-design` | https://github.com/anthropics/skills/tree/main/skills/frontend-design (Apache-2.0) | `dbd4588f9e1033efb41dad4bef2f7947c8993d44` | Design discipline and taste for every frontend task |
| `threejs-fundamentals`, `threejs-geometry`, `threejs-materials`, `threejs-lighting`, `threejs-animation`, `threejs-interaction`, `threejs-shaders`, `threejs-postprocessing`, `threejs-textures`, `threejs-loaders` | https://github.com/CloudAI-X/threejs-skills (MIT) | `b1c623076c661fc9b03dac19292e825a5d106823` | Three.js knowledge for the homepage hero (§13.12) only |
| `devsync-ui` | this repository (created in Phase 2 from §13) | — | DevSync's own design system; **wins over the others** |

## Overrides (binding)
- **`devsync-ui` and the spec win** wherever a skill disagrees (§0.4 rule 1). In particular,
  `frontend-design` encourages picking distinctive palettes and typefaces and warns against
  the "SaaS card kit"; DevSync's tokens (Inter, teal `#0F766E`, cards per §13.8) are fixed
  by the spec, so that skill supplies polish *within* those rules.
- **3D rules of §13.12 override the Three.js skills** (§0.4 rule 2): never load remote HDR
  environments, Draco/Basis decoders from CDNs (`gstatic.com`, `jsdelivr.net`) or external
  models/textures; the strict CSP blocks them anyway. Use generated geometry, `InstancedMesh`,
  local `Lightformer` environments and textures ≤ 256 px. `threejs-loaders` and
  `threejs-textures` are kept for reference only.
