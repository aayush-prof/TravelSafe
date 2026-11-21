import type { FactorKey } from "./types";

// Fixed categorical order (validated: dataviz palette slots 1–6). Colour follows the factor, never its rank.
export const FACTOR_COLOR: Record<FactorKey, string> = {
  crime: "#2a78d6",
  civil: "#eb6834",
  transport: "#1baf7a",
  disaster: "#eda100",
  weather: "#e87ba4",
  environment: "#008300",
};

export const FACTOR_SHORT: Record<FactorKey, string> = {
  crime: "Crime",
  civil: "Civil",
  transport: "Transport",
  disaster: "Hazards",
  weather: "Weather",
  environment: "Air",
};
