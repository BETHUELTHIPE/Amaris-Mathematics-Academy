"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { africanCountries, locationMessages, OTHER_LOCATION, type CountryLocations, type InitialLocation, type LocationErrors, type LocationValues } from "@/lib/location-data";

const cache = new Map<string, CountryLocations>();
const controlClass = "min-h-12 min-w-0 w-full rounded-xl border border-[#cbd6e5] bg-white px-3 py-3 text-base font-normal text-[#263852] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1f5bbd] disabled:bg-[#f5f7fb]";
async function fetchCountry(country: string): Promise<CountryLocations> {
  const cached = cache.get(country);
  if (cached) return cached;
  if (!africanCountries.some(item => item.code === country)) throw new Error("Unknown country");
  const response = await fetch("/data/locations/" + country + ".json?v=2026-10-22");
  if (!response.ok) throw new Error("Locations unavailable");
  const data = await response.json() as CountryLocations;
  cache.set(country, data);
  return data;
}

export function LocationFields({ initial, draftKey, returnTo, errors: serverErrors, showPicker = true, onEdit }: {
  initial: InitialLocation; draftKey?: string; returnTo: string; errors?: LocationErrors; showPicker?: boolean; onEdit?: (field: keyof LocationValues) => void;
}) {
  const [values, setValues] = useState<LocationValues>(() => ({ country: initial.country, province: initial.province, city: initial.city, provinceOther: initial.provinceOther, cityOther: initial.cityOther }));
  const [data, setData] = useState<CountryLocations | null>(initial.data);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [errors, setErrors] = useState<LocationErrors>({});
  const touched = useRef(false);
  const request = useRef(0);
  const storageKey = draftKey ? "amaris:safe-location:" + draftKey : null;
  useEffect(() => {
    let active = true;
    cache.set(initial.country, initial.data);
    if (storageKey && !initial.province) {
      try {
        const stored = JSON.parse(sessionStorage.getItem(storageKey) || "null") as { expiresAt: number; values: LocationValues } | null;
        if (stored && stored.expiresAt > Date.now() && africanCountries.some(item => item.code === stored.values.country)) {
          void fetchCountry(stored.values.country).then(restored => {
            if (!active || touched.current) return;
            const saved = stored.values;
            const province = saved.province === OTHER_LOCATION || Object.hasOwn(restored.provinces, saved.province) ? saved.province : "";
            const city = province && (saved.city === OTHER_LOCATION || restored.provinces[province]?.includes(saved.city)) ? saved.city : "";
            setValues({ country: saved.country, province, city, provinceOther: saved.provinceOther || "", cityOther: saved.cityOther || "" });
            setData(restored);
          }).catch(() => { /* A saved draft never blocks the live form. */ });
        }
      } catch { /* Invalid or unavailable session storage is optional. */ }
    }
    return () => { active = false; };
  }, [initial, storageKey]);

  function update(next: LocationValues) {
    touched.current = true;
    setValues(next);
    if (storageKey) {
      try { sessionStorage.setItem(storageKey, JSON.stringify({ expiresAt: Date.now() + 2 * 60 * 60 * 1000, values: next })); }
      catch { /* Private browsing must still permit form submission. */ }
    }
  }
  async function load(country: string) {
    const id = ++request.current;
    setLoading(true);
    setFailed(false);
    setData(null);
    try {
      const loaded = await fetchCountry(country);
      if (request.current === id) setData(loaded);
    } catch {
      if (request.current === id) setFailed(true);
    } finally {
      if (request.current === id) setLoading(false);
    }
  }
  function clearControl(field: HTMLInputElement | HTMLSelectElement) {
    if (!Object.hasOwn(locationMessages, field.name)) return;
    field.setCustomValidity("");
    setErrors(previous => ({ ...previous, [field.name]: undefined }));
    onEdit?.(field.name as keyof LocationValues);
  }
  function editOther(field: HTMLInputElement) {
    // Capture the typed value before validation updates can rerender a controlled input.
    const next = { ...values, [field.name]: field.value };
    clearControl(field);
    update(next);
  }
  function invalid(event: FormEvent<HTMLFieldSetElement>) {
    const field = event.target as HTMLInputElement | HTMLSelectElement;
    const name = field.name as keyof LocationValues;
    if (!Object.hasOwn(locationMessages, name)) return;
    field.setCustomValidity(locationMessages[name]);
    setErrors(previous => ({ ...previous, [name]: locationMessages[name] }));
  }
  const message = (field: keyof LocationValues) => serverErrors?.[field] || errors[field];
  const errorProps = (field: keyof LocationValues) => ({ "aria-invalid": Boolean(message(field)), "aria-describedby": message(field) ? field + "-error" : undefined });
  function error(field: keyof LocationValues) {
    return message(field) ? <p id={field + "-error"} role="alert" className="text-sm font-medium text-[#b42318]">{message(field)}</p> : null;
  }
  const provinces = data ? Object.keys(data.provinces) : [];
  const cities = data?.provinces[values.province] || [];
  return <fieldset className="grid min-w-0 gap-4" onInvalidCapture={invalid}>
    <legend className="mb-3 text-sm font-semibold text-[#263852]">Your location <span aria-hidden="true" className="text-[#b42318]">*</span></legend>
    {showPicker && <noscript><p className="mb-3 text-sm leading-6">Choose your location before completing this form. <a className="font-semibold underline" href={"/locations?returnTo=" + encodeURIComponent(returnTo)}>Choose country, province and city</a>.</p></noscript>}
    <div className="grid min-w-0 gap-4 sm:grid-cols-3">
      <div className="grid min-w-0 content-start gap-2"><label htmlFor="country" className="text-sm font-semibold text-[#263852]">Country</label>
        <select id="country" name="country" required autoComplete="country" value={values.country} className={controlClass} {...errorProps("country")} onChange={event => {
          const country = event.currentTarget.value;
          clearControl(event.currentTarget);
          for (const field of ["province", "city", "provinceOther", "cityOther"] as const) onEdit?.(field);
          update({ country, province: "", city: "", provinceOther: "", cityOther: "" });
          setErrors({});
          if (country) void load(country);
          else { ++request.current; setLoading(false); setFailed(false); setData(null); }
        }}><option value="">Choose country</option>{africanCountries.map(country => <option key={country.code} value={country.code}>{country.name}</option>)}</select>{error("country")}
      </div>
      <div className="grid min-w-0 content-start gap-2"><label htmlFor="province" className="text-sm font-semibold text-[#263852]">Province / Region</label>
        <select id="province" name="province" required autoComplete="address-level1" value={values.province} disabled={!values.country || loading || failed} className={controlClass} {...errorProps("province")} onChange={event => {
          const province = event.currentTarget.value;
          clearControl(event.currentTarget);
          for (const field of ["provinceOther", "city", "cityOther"] as const) onEdit?.(field);
          update({ ...values, province, provinceOther: "", city: "", cityOther: "" });
          setErrors(previous => ({ ...previous, province: undefined, provinceOther: undefined, city: undefined, cityOther: undefined }));
        }}><option value="">{loading ? "Loading regions…" : "Choose province / region"}</option>{provinces.map(province => <option key={province} value={province}>{province}</option>)}<option value={OTHER_LOCATION}>Other province / region</option></select>{error("province")}
        {values.province === OTHER_LOCATION && <><label htmlFor="provinceOther" className="text-sm font-semibold">Province / Region name</label><input id="provinceOther" name="provinceOther" required maxLength={160} value={values.provinceOther} autoComplete="address-level1" className={controlClass} {...errorProps("provinceOther")} onChange={event => editOther(event.currentTarget)} />{error("provinceOther")}</>}
      </div>
      <div className="grid min-w-0 content-start gap-2"><label htmlFor="city" className="text-sm font-semibold text-[#263852]">City / Town</label>
        <select id="city" name="city" required autoComplete="address-level2" value={values.city} disabled={!values.province || loading || failed} className={controlClass} {...errorProps("city")} onChange={event => {
          const city = event.currentTarget.value;
          clearControl(event.currentTarget);
          onEdit?.("cityOther");
          update({ ...values, city, cityOther: "" });
        }}><option value="">Choose city / town</option>{cities.map(city => <option key={city} value={city}>{city}</option>)}<option value={OTHER_LOCATION}>Other city / town</option></select>{error("city")}
        {values.city === OTHER_LOCATION && <><label htmlFor="cityOther" className="text-sm font-semibold">City / Town name</label><input id="cityOther" name="cityOther" required maxLength={160} value={values.cityOther} autoComplete="address-level2" className={controlClass} {...errorProps("cityOther")} onChange={event => editOther(event.currentTarget)} />{error("cityOther")}</>}
      </div>
    </div>
    {loading && <p role="status" className="text-sm text-[#52617a]">Loading provinces and cities…</p>}
    {failed && <p role="alert" className="text-sm text-[#b42318]">Location choices could not be loaded. <button type="button" className="min-h-11 font-semibold underline" onClick={() => void load(values.country)}>Try again</button></p>}
    <p className="text-xs leading-5 text-[#60708a]">Choose “Other” if your province or city is not listed. Place names: <a href="https://www.geonames.org/" className="underline" target="_blank" rel="noreferrer">GeoNames</a> (<a href="https://creativecommons.org/licenses/by/4.0/" className="underline" target="_blank" rel="noreferrer">CC BY 4.0</a>).</p>
  </fieldset>;
}
