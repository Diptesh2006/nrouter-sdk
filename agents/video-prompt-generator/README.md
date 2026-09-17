# nRouter Video Prompt Generator SDK

This package exposes `generateVideoPrompt(options)`, an SDK utility that generates production-ready
video prompts for Google Flow, Higgsfield, Veo, Runway, Luma Dream Machine, and Sora.

## Brand & Skill Integration

**How Video Skills are Incorporated:**
Video generation tools require clear subject continuity, camera movement, timing, lighting, and
negative constraints. The agent adapts its prompt to the selected `videoModel` or platform. It
generates a brief for the user to paste into that tool; it does not control or publish inside a
third-party platform.

## Local Playwright Testing

To run the Playwright end-to-end test suite:
```bash
NROUTER_API_KEY="sk-nrouter-..." npm run e2e
```


## 🛠️ How to Tweak Skills & Agent Memory

This agent is powered by a configurable "Skills & Memory" markdown file, rather than hardcoded logic. This allows design and content teams to update the agent's behavior without modifying the TypeScript codebase.

1. **Locate the Skills File**: Open `skills/instructions.md`.
2. **Tweak the Guidelines**: Modify the brand colors, tone of voice, visual aesthetics, or negative prompts directly in the markdown.
3. **Deploy as a Package**: Because the `skills/` directory is explicitly whitelisted in the `package.json` `"files"` array, any changes you make to `instructions.md` will be automatically bundled when you run `npm publish`.

When installed externally via NPM, the agent will dynamically read from its packaged `skills/instructions.md` file at runtime!
