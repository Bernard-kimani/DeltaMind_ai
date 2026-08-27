import type { Track } from "./api/types";

// This entire frontend instance runs locked to exactly one track — no UI
// anywhere in this codebase should offer to switch, compare, or even name
// the other track. Set via VITE_ACTIVE_TRACK (see .env.track1/.env.track4
// and package.json's dev:track1/dev:track4/build:track1/build:track4
// scripts) so running two instances during testing, or building the one
// instance that actually ships for the hackathon submission, is a build
// flag — not a UI control a judge could ever see or touch.
const raw = import.meta.env.VITE_ACTIVE_TRACK as string | undefined;

if (!raw) {
  // eslint-disable-next-line no-console
  console.warn("VITE_ACTIVE_TRACK not set — defaulting to track1_alpha_spreads. Run via `npm run dev:track1` or `dev:track4`.");
}

export const ACTIVE_TRACK: Track = (raw as Track) ?? "track1_alpha_spreads";
