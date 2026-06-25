// Per-vertical configuration — the research (docs/research/01 + 02 + 04) encoded as data.
// Drives scoring tier, pricing multiplier, ROI avg-ticket, default site theme, and section order.
// Numbers are directional benchmarks (see research caveats); tune in one place.

export type Tier = "A" | "B" | "C" | "D";
export type ThemeId = "warm-boutique" | "luxe-dark" | "modern-clean" | "bold-field";

export interface VerticalConfig {
  key: string;                 // normalized vertical key
  label: string;
  tier: Tier;                  // A=call first ... D=avoid
  categoryScore: number;       // 0–1, the "category value" sub-score (A~1.0 ... D~0.2)
  industryMult: number;        // pricing multiplier 0.8–2.0 (Research 02)
  avgNewCustomerValue: number; // USD, for ROI math (Research 01)
  defaultTheme: ThemeId;
  altTheme: ThemeId;           // the contrasting second option
  // Google Places "types"/text terms that map to this vertical:
  placesTypes: string[];
  searchTerms: string[];
  // rough monthly local searchers seed for ROI (very approximate; refine later):
  monthlySearchersSeed: number;
  sectionOrder: string[];
}

// Section block keys must match lib/site-blocks/ (Plan 05).
const MEDSPA_SECTIONS = ["header","hero","trustStrip","services","about","beforeAfter","pricing","testimonials","bookingCta","faq","map","footer"];
const TRADES_SECTIONS = ["header","hero","trustStrip","services","serviceArea","about","beforeAfter","testimonials","pricing","bookingCta","footer"];
const MEDICAL_SECTIONS = ["header","hero","trustStrip","services","about","testimonials","gallery","faq","bookingCta","map","footer"];
const LAW_SECTIONS = ["header","hero","services","about","testimonials","gallery","bookingCta","map","footer"];

export const VERTICALS: VerticalConfig[] = [
  // ---- A tier: high LTV, cash-pay, image-sensitive, strong margins ----
  { key:"med_spa", label:"Med Spa / Aesthetics", tier:"A", categoryScore:1.0, industryMult:1.9, avgNewCustomerValue:9000, defaultTheme:"warm-boutique", altTheme:"luxe-dark", placesTypes:["spa","beauty_salon"], searchTerms:["med spa","medical spa","aesthetics clinic"], monthlySearchersSeed:90, sectionOrder:MEDSPA_SECTIONS },
  { key:"plastic_surgery", label:"Cosmetic / Plastic Surgery", tier:"A", categoryScore:1.0, industryMult:2.0, avgNewCustomerValue:9000, defaultTheme:"luxe-dark", altTheme:"warm-boutique", placesTypes:["doctor","health"], searchTerms:["plastic surgeon","cosmetic surgery"], monthlySearchersSeed:60, sectionOrder:MEDSPA_SECTIONS },
  { key:"dentist", label:"Dental (General)", tier:"A", categoryScore:0.95, industryMult:1.9, avgNewCustomerValue:1200, defaultTheme:"modern-clean", altTheme:"warm-boutique", placesTypes:["dentist"], searchTerms:["dentist","dental office"], monthlySearchersSeed:140, sectionOrder:MEDICAL_SECTIONS },
  { key:"orthodontist", label:"Orthodontist", tier:"A", categoryScore:0.95, industryMult:1.9, avgNewCustomerValue:5800, defaultTheme:"modern-clean", altTheme:"warm-boutique", placesTypes:["dentist"], searchTerms:["orthodontist","braces","invisalign"], monthlySearchersSeed:70, sectionOrder:MEDICAL_SECTIONS },
  { key:"dermatology", label:"Dermatology", tier:"A", categoryScore:0.9, industryMult:1.8, avgNewCustomerValue:1500, defaultTheme:"modern-clean", altTheme:"warm-boutique", placesTypes:["doctor"], searchTerms:["dermatologist","skin clinic"], monthlySearchersSeed:90, sectionOrder:MEDICAL_SECTIONS },
  { key:"fertility", label:"Fertility / IVF", tier:"A", categoryScore:0.95, industryMult:2.0, avgNewCustomerValue:30000, defaultTheme:"modern-clean", altTheme:"warm-boutique", placesTypes:["doctor","health"], searchTerms:["fertility clinic","ivf"], monthlySearchersSeed:30, sectionOrder:MEDICAL_SECTIONS },
  { key:"pi_law", label:"Personal Injury Law", tier:"A", categoryScore:0.9, industryMult:2.0, avgNewCustomerValue:15000, defaultTheme:"luxe-dark", altTheme:"modern-clean", placesTypes:["lawyer"], searchTerms:["personal injury lawyer","accident attorney"], monthlySearchersSeed:80, sectionOrder:LAW_SECTIONS },

  // ---- B tier: high-ticket trades + solid recurring/medical ----
  { key:"roofing", label:"Roofing", tier:"B", categoryScore:0.75, industryMult:1.4, avgNewCustomerValue:12000, defaultTheme:"bold-field", altTheme:"modern-clean", placesTypes:["roofing_contractor","general_contractor"], searchTerms:["roofer","roofing company"], monthlySearchersSeed:110, sectionOrder:TRADES_SECTIONS },
  { key:"hvac", label:"HVAC", tier:"B", categoryScore:0.78, industryMult:1.4, avgNewCustomerValue:9000, defaultTheme:"bold-field", altTheme:"modern-clean", placesTypes:["hvac_contractor"], searchTerms:["hvac","air conditioning repair","heating and cooling"], monthlySearchersSeed:180, sectionOrder:TRADES_SECTIONS },
  { key:"remodeling", label:"Kitchen & Bath / GC", tier:"B", categoryScore:0.75, industryMult:1.4, avgNewCustomerValue:30000, defaultTheme:"bold-field", altTheme:"warm-boutique", placesTypes:["general_contractor"], searchTerms:["kitchen remodel","bathroom remodel","general contractor"], monthlySearchersSeed:90, sectionOrder:TRADES_SECTIONS },
  { key:"pool_builder", label:"Pool Builder", tier:"B", categoryScore:0.72, industryMult:1.45, avgNewCustomerValue:65000, defaultTheme:"bold-field", altTheme:"warm-boutique", placesTypes:["general_contractor"], searchTerms:["pool builder","inground pool"], monthlySearchersSeed:50, sectionOrder:TRADES_SECTIONS },
  { key:"window_install", label:"Window / Door Install", tier:"B", categoryScore:0.7, industryMult:1.35, avgNewCustomerValue:9000, defaultTheme:"bold-field", altTheme:"modern-clean", placesTypes:["general_contractor"], searchTerms:["window replacement","window installer"], monthlySearchersSeed:70, sectionOrder:TRADES_SECTIONS },
  { key:"plumbing", label:"Plumbing", tier:"B", categoryScore:0.68, industryMult:1.2, avgNewCustomerValue:1500, defaultTheme:"bold-field", altTheme:"modern-clean", placesTypes:["plumber"], searchTerms:["plumber","plumbing"], monthlySearchersSeed:180, sectionOrder:TRADES_SECTIONS },
  { key:"chiropractor", label:"Chiropractor", tier:"B", categoryScore:0.7, industryMult:1.3, avgNewCustomerValue:4500, defaultTheme:"modern-clean", altTheme:"warm-boutique", placesTypes:["chiropractor"], searchTerms:["chiropractor"], monthlySearchersSeed:90, sectionOrder:MEDICAL_SECTIONS },
  { key:"physical_therapy", label:"Physical Therapy", tier:"B", categoryScore:0.65, industryMult:1.2, avgNewCustomerValue:700, defaultTheme:"modern-clean", altTheme:"warm-boutique", placesTypes:["physiotherapist"], searchTerms:["physical therapy","physical therapist"], monthlySearchersSeed:80, sectionOrder:MEDICAL_SECTIONS },
  { key:"veterinary", label:"Veterinary", tier:"B", categoryScore:0.68, industryMult:1.25, avgNewCustomerValue:1500, defaultTheme:"warm-boutique", altTheme:"modern-clean", placesTypes:["veterinary_care"], searchTerms:["veterinarian","animal hospital"], monthlySearchersSeed:90, sectionOrder:MEDICAL_SECTIONS },
  { key:"family_law", label:"Family / Estate Law", tier:"B", categoryScore:0.7, industryMult:1.6, avgNewCustomerValue:7500, defaultTheme:"luxe-dark", altTheme:"modern-clean", placesTypes:["lawyer"], searchTerms:["family law attorney","divorce lawyer","estate planning"], monthlySearchersSeed:70, sectionOrder:LAW_SECTIONS },
  { key:"landscaping", label:"Landscaping / Hardscaping", tier:"B", categoryScore:0.65, industryMult:1.25, avgNewCustomerValue:8000, defaultTheme:"bold-field", altTheme:"warm-boutique", placesTypes:["landscaper"], searchTerms:["landscaping","hardscaping","lawn care"], monthlySearchersSeed:100, sectionOrder:TRADES_SECTIONS },
  { key:"pest_control", label:"Pest Control", tier:"B", categoryScore:0.65, industryMult:1.2, avgNewCustomerValue:2000, defaultTheme:"bold-field", altTheme:"modern-clean", placesTypes:["pest_control_service"], searchTerms:["pest control","exterminator"], monthlySearchersSeed:120, sectionOrder:TRADES_SECTIONS },
  { key:"garage_door", label:"Garage Door", tier:"B", categoryScore:0.66, industryMult:1.3, avgNewCustomerValue:1400, defaultTheme:"bold-field", altTheme:"modern-clean", placesTypes:["general_contractor"], searchTerms:["garage door repair","garage door installer"], monthlySearchersSeed:110, sectionOrder:TRADES_SECTIONS },
  { key:"accountant", label:"Accountant / CPA", tier:"B", categoryScore:0.68, industryMult:1.3, avgNewCustomerValue:15000, defaultTheme:"modern-clean", altTheme:"luxe-dark", placesTypes:["accounting"], searchTerms:["cpa","accountant","tax preparation"], monthlySearchersSeed:80, sectionOrder:MEDICAL_SECTIONS },
  { key:"gym", label:"Gym / Fitness Studio", tier:"B", categoryScore:0.62, industryMult:1.15, avgNewCustomerValue:4320, defaultTheme:"luxe-dark", altTheme:"bold-field", placesTypes:["gym"], searchTerms:["gym","fitness studio","personal training"], monthlySearchersSeed:120, sectionOrder:TRADES_SECTIONS },
  { key:"painter", label:"Painter", tier:"B", categoryScore:0.64, industryMult:1.3, avgNewCustomerValue:7500, defaultTheme:"bold-field", altTheme:"warm-boutique", placesTypes:["painter"], searchTerms:["house painter","painting contractor"], monthlySearchersSeed:90, sectionOrder:TRADES_SECTIONS },

  // ---- C tier: solid volume, lower ticket/margin ----
  { key:"electrician", label:"Electrician", tier:"C", categoryScore:0.5, industryMult:1.15, avgNewCustomerValue:1500, defaultTheme:"bold-field", altTheme:"modern-clean", placesTypes:["electrician"], searchTerms:["electrician","electrical contractor"], monthlySearchersSeed:120, sectionOrder:TRADES_SECTIONS },
  { key:"auto_repair", label:"Auto Repair / Body", tier:"C", categoryScore:0.45, industryMult:1.0, avgNewCustomerValue:4500, defaultTheme:"bold-field", altTheme:"modern-clean", placesTypes:["car_repair"], searchTerms:["auto repair","mechanic","body shop"], monthlySearchersSeed:150, sectionOrder:TRADES_SECTIONS },
  { key:"salon", label:"Hair Salon / Barbershop", tier:"C", categoryScore:0.45, industryMult:0.95, avgNewCustomerValue:1500, defaultTheme:"warm-boutique", altTheme:"luxe-dark", placesTypes:["hair_care","beauty_salon"], searchTerms:["hair salon","barbershop"], monthlySearchersSeed:140, sectionOrder:MEDSPA_SECTIONS },
  { key:"solar", label:"Solar Installer", tier:"C", categoryScore:0.5, industryMult:1.3, avgNewCustomerValue:23400, defaultTheme:"bold-field", altTheme:"modern-clean", placesTypes:["general_contractor"], searchTerms:["solar installer","solar panels"], monthlySearchersSeed:60, sectionOrder:TRADES_SECTIONS },

  // ---- D tier: avoid as primary (thin margin / churn / saturation) ----
  { key:"restaurant", label:"Restaurant (independent)", tier:"D", categoryScore:0.2, industryMult:0.9, avgNewCustomerValue:120, defaultTheme:"luxe-dark", altTheme:"warm-boutique", placesTypes:["restaurant"], searchTerms:["restaurant"], monthlySearchersSeed:200, sectionOrder:["header","hero","menu","about","gallery","reservations","map","footer"] },
];

export const VERTICAL_BY_KEY: Record<string, VerticalConfig> =
  Object.fromEntries(VERTICALS.map((v) => [v.key, v]));

// Default scan set = A and B tier (call-first targets). C added on request; D excluded.
export const DEFAULT_SCAN_KEYS = VERTICALS.filter((v) => v.tier === "A" || v.tier === "B").map((v) => v.key);

// Map raw Google Places `types` to our vertical key (first match wins; refine with searchTerm context).
export function classifyVertical(rawTypes: string[]): string | null {
  for (const v of VERTICALS) {
    if (v.placesTypes.some((t) => rawTypes.includes(t))) return v.key;
  }
  return null;
}
