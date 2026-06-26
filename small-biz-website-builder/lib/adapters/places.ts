// Google Places API (New) adapter — mock-first pattern (Plan 01, Research 05).
// Real impl uses Text Search (New) at places.googleapis.com/v1 with an X-Goog-FieldMask.
// Requesting rating/userRatingCount/websiteUri bills at the Enterprise SKU (unavoidable).

import { MOCK_MODE } from "../config";

export interface PlaceCandidate {
  placeId: string;
  name: string;
  rawTypes: string[];
  rating?: number;
  reviewCount?: number;
  priceLevel?: number;
  websiteUri?: string;     // ABSENCE is the "no website" signal (verify with classifier)
  phone?: string;
  address?: string;
  lat?: number;
  lng?: number;
}

export interface TextSearchParams {
  textQuery: string;       // e.g. "med spa in 90210"
  lat: number; lng: number; radiusMeters?: number;
  includedType?: string;
}

const FIELD_MASK = [
  "places.id","places.displayName","places.types","places.rating","places.userRatingCount",
  "places.priceLevel","places.websiteUri","places.nationalPhoneNumber","places.formattedAddress",
  "places.location","nextPageToken",
].join(",");

export async function textSearch(params: TextSearchParams): Promise<{ candidates: PlaceCandidate[]; capped: boolean }> {
  if (MOCK_MODE) return mockTextSearch(params);

  const res = await fetch("https://places.googleapis.com/v1/places:searchText", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Goog-Api-Key": process.env.GOOGLE_MAPS_API_KEY ?? "",
      "X-Goog-FieldMask": FIELD_MASK,
    },
    body: JSON.stringify({
      textQuery: params.textQuery,
      ...(params.includedType ? { includedType: params.includedType } : {}),
      locationBias: { circle: { center: { latitude: params.lat, longitude: params.lng }, radius: params.radiusMeters ?? 8000 } },
      pageSize: 20,
    }),
  });
  if (!res.ok) throw new Error(`Places searchText ${res.status}`);
  const data = await res.json();
  const candidates: PlaceCandidate[] = (data.places ?? []).map(mapPlace);
  // NOTE: implement nextPageToken pagination (max 3 pages = 60). Set capped=true when a 3rd
  // page token still exists — surface it, never silently truncate (Plan 03).
  return { candidates, capped: Boolean(data.nextPageToken) };
}

function mapPlace(p: any): PlaceCandidate {
  return {
    placeId: p.id,
    name: p.displayName?.text ?? "",
    rawTypes: p.types ?? [],
    rating: p.rating,
    reviewCount: p.userRatingCount,
    priceLevel: typeof p.priceLevel === "string" ? priceLevelToInt(p.priceLevel) : p.priceLevel,
    websiteUri: p.websiteUri,
    phone: p.nationalPhoneNumber,
    address: p.formattedAddress,
    lat: p.location?.latitude,
    lng: p.location?.longitude,
  };
}

function priceLevelToInt(s: string): number | undefined {
  return { PRICE_LEVEL_INEXPENSIVE:1, PRICE_LEVEL_MODERATE:2, PRICE_LEVEL_EXPENSIVE:3, PRICE_LEVEL_VERY_EXPENSIVE:4 }[s];
}

// --- Mock fixtures: a few website-less, well-reviewed businesses for demoing free ---
function mockTextSearch(params: TextSearchParams): { candidates: PlaceCandidate[]; capped: boolean } {
  // San Antonio, TX seed market (Stone Oak / Alamo Heights area) — see lib/seedMarkets.ts
  const seed: PlaceCandidate[] = [
    { placeId:"mock_medspa_1", name:"Lumière Med Spa", rawTypes:["spa","beauty_salon"], rating:4.8, reviewCount:180, priceLevel:3, phone:"(210) 555-2840", address:"1604 Stone Oak Pkwy, San Antonio, TX 78258", lat:params.lat, lng:params.lng /* no websiteUri => prospect */ },
    { placeId:"mock_dent_1", name:"Alamo Heights Family Dental", rawTypes:["dentist"], rating:4.7, reviewCount:96, priceLevel:2, phone:"(210) 555-1199", address:"5100 Broadway St, San Antonio, TX 78209", lat:params.lat, lng:params.lng, websiteUri:"https://facebook.com/ahfamilydental" /* social_only */ },
    { placeId:"mock_hvac_1", name:"Summit Heating & Air", rawTypes:["hvac_contractor"], rating:4.9, reviewCount:142, priceLevel:2, phone:"(210) 555-7720", address:"18250 Blanco Rd, San Antonio, TX 78258", lat:params.lat, lng:params.lng /* no website */ },
    { placeId:"mock_real_1", name:"Established Roofing Co", rawTypes:["roofing_contractor"], rating:4.5, reviewCount:64, priceLevel:2, phone:"(210) 555-3300", address:"123 Loop 410, San Antonio, TX 78216", lat:params.lat, lng:params.lng, websiteUri:"https://establishedroofing.com" /* real => filtered out */ },
  ];
  const q = params.textQuery.toLowerCase();
  const candidates = seed.filter((c) => c.rawTypes.some((t) => q.includes(t.split("_")[0])) || true);
  return { candidates, capped: false };
}
