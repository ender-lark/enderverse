// "No website" classifier (Plan 03, Research 05).
// Pass 1: classify the websiteUri (if any). Pass 2 (HTTP probe) is done in the engine for survivors.

import type { WebsiteStatus } from "./scoring";

const SOCIAL = ["facebook.com","instagram.com","tiktok.com","twitter.com","x.com","youtube.com"];
const LINK_IN_BIO = ["linktr.ee","linkin.bio","beacons.ai","carrd.co","bio.link"];
const DIRECTORY = ["yelp.com","opentable.com","vagaro.com","booksy.com","healthgrades.com","zocdoc.com","thumbtack.com","angi.com","nextdoor.com","tripadvisor.com","doordash.com","ubereats.com","grubhub.com"];
const PLACEHOLDER = ["business.site","sites.google.com","godaddysites.com","wixsite.com","weebly.com","square.site"];

function etldPlusOne(url: string): string {
  try {
    const u = new URL(url.startsWith("http") ? url : `https://${url}`);
    const host = u.hostname.replace(/^www\./, "").toLowerCase();
    const parts = host.split(".");
    return parts.length > 2 ? parts.slice(-2).join(".") : host;
  } catch {
    return "";
  }
}

/** Pass 1 — classify from the URL alone. Returns a non-"none" status when a URL exists. */
export function classifyWebsiteUrl(websiteUri?: string | null): WebsiteStatus {
  if (!websiteUri) return "none";
  const host = new URL(websiteUri.startsWith("http") ? websiteUri : `https://${websiteUri}`).hostname.replace(/^www\./, "").toLowerCase();
  const base = etldPlusOne(websiteUri);
  if (SOCIAL.includes(base)) return "social_only";
  if (LINK_IN_BIO.includes(base)) return "social_only";
  if (DIRECTORY.includes(base)) return "directory_only";
  if (PLACEHOLDER.some((p) => host.endsWith(p))) return "placeholder_dead";
  return "real"; // pending HTTP probe (Pass 2) before final acceptance
}

/** Is this prospect-worthy (i.e. NOT a real working site)? */
export function isProspectStatus(s: WebsiteStatus): boolean {
  return s !== "real";
}

// Pass 2 (engine): for "real" candidates, HEAD->GET, follow redirects, check the redirect target's
// eTLD+1 against the lists above and for parked-page markers; a TLS error is a weak negative.
// Keep network calls out of this pure module so it stays unit-testable.
