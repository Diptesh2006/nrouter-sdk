# nRouter Brand and Video Rules

These runtime rules are a curated copy of the frontend brand and video skills from
nRouterGateway/nrouter-frontend-ui, reviewed at commit 150076c8. They keep generated
prompts self-contained when the agent is installed from npm.

## Brand

- Use only the canonical lowercase `n` gateway mark from the approved brand kit. Never redraw,
  trace, invent, or AI-generate the logo. In the frontend source this is resolved from
  `resources/brand-kit/Logos/`.
- For video watermarks, use the supplied bottom-left wordmark asset on dark footage. Never make
  a large replacement title or a screenshot-derived logo.
- Choose the approved wordmark variant by background: black on light, white on dark, and the
  brand light/dark lockup when both mark and wordmark are needed. Use the icon variant only for
  icon-shaped surfaces.
- Use Obsidian (#0a0a0b), white (#ffffff), and coral (#FF6C5E) for primary brand meaning.
- Use mint (#90FCA6) sparingly as a hairline, underbar, or small UI accent; never as a large fill.
- For video compositions, warm paper (#fffefa) and warm ink (#211f1b) are allowed as the light
  editorial surface. Mint remains an accent, not a background.
- Use Geist for display and body copy and Geist Mono for metrics, code, and numeric readouts.
- Use restrained, legible product surfaces: dark-mode controls, routing, latency, cost, and
  model information should look like a real operational interface.
- Use sentence case and clear, factual language. Do not claim certifications, capabilities,
  performance numbers, or provider support unless the input explicitly establishes them.
- Do not expose API keys, private provider names, internal topology, private headers, or secrets.

## Cinematic Direction

- Prefer precise camera movement with physical weight: dolly, crane, lateral track, or locked-off
  composition. Avoid random floating camera motion.
- Default to 4K UHD, 24fps, clean blacks, natural saturation, controlled highlights, and subtle
  film texture. Use motivated lighting and readable UI contrast.
- Keep the nRouter product and its routing/observability value visible without turning the scene
  into a generic abstract AI montage.

## Video Delivery Rules

- Keep the foundation clean and readable: one focal subject, one reading direction, generous
  negative space, and captions planned for muted playback.
- Show real product UI only from approved references or supplied captures. Label simulated UI,
  routing states, and metrics as illustrative when they are not verified live data.
- Do not show real API keys. Use `sk-nrouter-xxxx` in sample code. Do not expose private provider
  names, internal headers, ports, topology, database details, or credentials.
- Do not claim SOC 2 completion, guaranteed latency, universal provider support, or automatic
  failover unless approved product facts are provided with the request.
