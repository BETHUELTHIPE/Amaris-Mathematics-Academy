/** Choose the clearest available English system/browser speech voice.
 * No recorded data or speech is sent to an Amaris server by this helper.
 * Voice quality and the available accents depend on the visitor's device.
 */
export type VoiceChoice = Pick<SpeechSynthesisVoice, "name" | "lang" | "voiceURI" | "default" | "localService">;

function voiceScore(voice: VoiceChoice): number {
  const language = voice.lang.replace(/_/g, "-").toLowerCase();
  if (language !== "en" && !language.startsWith("en-")) return -10000;

  let score = 70;
  if (language === "en-za") score += 50;
  else if (language === "en-gb") score += 42;
  else if (language === "en-au") score += 38;
  else if (language === "en-us") score += 32;

  const name = voice.name.toLowerCase();
  if (/natural|neural|premium|enhanced|high.quality/.test(name)) score += 70;
  if (/google|microsoft|siri|apple/.test(name)) score += 30;
  if (/espeak|festival|flite|robot/.test(name)) score -= 100;
  if (voice.default) score += 5;
  return score;
}

export function rankedEnglishVoices<T extends VoiceChoice>(voices: readonly T[]): T[] {
  return voices
    .filter((voice) => voiceScore(voice) > -10000)
    .sort((first, second) => voiceScore(second) - voiceScore(first) || first.name.localeCompare(second.name));
}

export function selectEnglishVoice<T extends VoiceChoice>(
  voices: readonly T[],
  requestedURI: string | null = null,
): T | null {
  const ranked = rankedEnglishVoices(voices);
  if (requestedURI) {
    const selected = ranked.find((voice) => voice.voiceURI === requestedURI);
    if (selected) return selected;
  }
  return ranked[0] ?? null;
}
