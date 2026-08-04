// Facet geometry copied verbatim (point-for-point) from
// design_handoff_logo/assets/sema-mark-{brand,inverse,mono}.svg -- the three
// asset files share identical polygon points in identical order and differ
// only in fill, so a single array can drive all three variants. Lives in its
// own module (not inline in Logo.tsx) so consumers of just the geometry --
// the login split-panel's decorative background facets, login_redesign_
// prompt.md -- don't import it through a component file, which would also
// break Logo.tsx's React Fast Refresh (a component file may only export
// components for that to work).
import { BRAND } from "../../lib/tokens";

export const MARK_FACETS: { points: string; brand: string; inverse: string; monoOpacity: number }[] = [
  { points: "67.0,4.0 104.0,7.0 72.0,35.0", brand: BRAND.lavender, inverse: "#8187F2", monoOpacity: 0.65 },
  { points: "120.0,4.0 157.0,7.0 143.0,37.0 119.0,7.0", brand: BRAND.yellow, inverse: "#F4D165", monoOpacity: 0.8 },
  { points: "80.0,37.0 112.0,6.0 137.0,42.0 80.0,41.0", brand: BRAND.coral, inverse: "#F4998E", monoOpacity: 0.73 },
  { points: "163.0,7.0 211.0,54.0 211.0,58.0 150.0,43.0", brand: BRAND.yellow, inverse: "#F4D165", monoOpacity: 0.9 },
  { points: "64.0,12.0 66.0,43.0 14.0,57.0", brand: BRAND.lavender, inverse: "#8187F2", monoOpacity: 0.56 },
  { points: "77.0,45.0 140.0,47.0 106.0,106.0 101.0,103.0", brand: BRAND.lavender400, inverse: "#A3AAFF", monoOpacity: 0.72 },
  { points: "8.0,64.0 62.0,49.0 22.0,106.0 4.0,69.0", brand: BRAND.lavender, inverse: "#8187F2", monoOpacity: 0.52 },
  { points: "26.0,106.0 69.0,49.0 75.0,54.0 98.0,110.0 26.0,110.0", brand: BRAND.lavender600, inverse: "#676EDC", monoOpacity: 0.61 },
  { points: "145.0,49.0 184.0,110.0 109.0,109.0", brand: BRAND.coral, inverse: "#F4998E", monoOpacity: 0.82 },
  { points: "153.0,49.0 215.0,67.0 192.0,107.0 187.0,105.0 152.0,52.0", brand: BRAND.yellow, inverse: "#F4D165", monoOpacity: 0.92 },
  { points: "30.0,115.0 88.0,118.0 48.0,134.0 29.0,118.0", brand: BRAND.lavender600, inverse: "#676EDC", monoOpacity: 0.59 },
  { points: "107.0,115.0 159.0,119.0 102.0,130.0", brand: BRAND.lavender600, inverse: "#676EDC", monoOpacity: 0.77 },
  { points: "51.0,138.0 99.0,118.0 98.0,135.0 52.0,181.0", brand: BRAND.lavender600, inverse: "#676EDC", monoOpacity: 0.62 },
];
