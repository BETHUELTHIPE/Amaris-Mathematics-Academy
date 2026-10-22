import { africanCountries, locationMessages, OTHER_LOCATION, type CountryLocations, type InitialLocation, type LocationErrors, type LocationValues } from "./location-data";
import { countryLoaders } from "./location-loaders";

export async function loadCountry(code: string): Promise<CountryLocations | null> {
  if (!Object.hasOwn(countryLoaders, code)) return null;
  const loader = countryLoaders[code as keyof typeof countryLoaders];
  return loader ? (await loader()).default : null;
}
export async function parseLocation(values: Record<string, unknown>) {
  const value = (name: keyof LocationValues) => typeof values[name] === "string" ? (values[name] as string).trim().normalize("NFC") : "";
  const raw = { country: value("country"), province: value("province"), city: value("city"), provinceOther: value("provinceOther"), cityOther: value("cityOther") };
  const errors: LocationErrors = {};
  const data = await loadCountry(raw.country);
  if (!raw.country) errors.country = locationMessages.country;
  else if (!data) errors.country = "Please choose an African country from the list.";
  if (!raw.province) errors.province = locationMessages.province;
  else if (raw.province === OTHER_LOCATION) {
    if (!raw.provinceOther || raw.provinceOther.length > 160) errors.provinceOther = locationMessages.provinceOther;
  } else if (!data || !Object.hasOwn(data.provinces, raw.province)) errors.province = "Please choose a province or region in your selected country.";
  if (!raw.city) errors.city = locationMessages.city;
  else if (raw.city === OTHER_LOCATION) {
    if (!raw.cityOther || raw.cityOther.length > 160) errors.cityOther = locationMessages.cityOther;
  } else if (!data || !Object.hasOwn(data.provinces, raw.province) || !data.provinces[raw.province].includes(raw.city)) errors.city = "Please choose a city or town in your selected province.";
  return { errors, raw, value: Object.keys(errors).length ? null : {
    country: raw.country,
    province: raw.province === OTHER_LOCATION ? raw.provinceOther : raw.province,
    city: raw.city === OTHER_LOCATION ? raw.cityOther : raw.city,
  }};
}
export async function initialLocation(params: Partial<Record<keyof LocationValues, unknown>> = {}): Promise<InitialLocation> {
  const country = typeof params.country === "string" && africanCountries.some(item => item.code === params.country) ? params.country : "ZA";
  const data = (await loadCountry(country))!;
  const parsed = await parseLocation({ ...params, country });
  return { country, province: parsed.raw.province === OTHER_LOCATION || !parsed.errors.province ? parsed.raw.province : "",
    city: parsed.raw.city === OTHER_LOCATION || !parsed.errors.city ? parsed.raw.city : "",
    provinceOther: parsed.raw.provinceOther, cityOther: parsed.raw.cityOther, data };
}

