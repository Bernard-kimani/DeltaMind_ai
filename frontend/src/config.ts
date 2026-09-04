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

// Submission-demo flag (2026-09-04): every page that lets you switch
// tracks (App's top nav, Performance's toggle, Logs' toggle) hides Track
// 1/4 and locks to Track 5 alone -- today's actively-engineered, currently-
// running track -- instead of presenting three tracks and diluting the
// story for judges. Nothing behind this flag is deleted; flip back to
// false to restore the full multi-track dashboard everywhere at once.
export const DEMO_SINGLE_TRACK = true;
export const DEMO_TRACK = "track5_momentum_swing";
