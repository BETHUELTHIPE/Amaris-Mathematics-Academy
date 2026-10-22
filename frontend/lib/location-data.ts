import countries from "../data/locations/index.json";

export const africanCountries = countries;
export const OTHER_LOCATION = "__other__";
export const locationFields = ["country", "province", "city"] as const;
export type LocationField = typeof locationFields[number];
export type LocationValues = { country: string; province: string; city: string; provinceOther: string; cityOther: string };
export type LocationErrors = Partial<Record<keyof LocationValues, string>>;
export type CountryLocations = { name: string; provinces: Record<string, string[]> };
export type InitialLocation = LocationValues & { data: CountryLocations };
export const locationMessages = {
  country: "Please choose your country.",
  province: "Please choose your province or region.",
  city: "Please choose your city or town.",
  provinceOther: "Please enter your province or region.",
  cityOther: "Please enter your city or town.",
};
export function countryName(code: string) {
  return africanCountries.find(country => country.code === code)?.name || code;
}

