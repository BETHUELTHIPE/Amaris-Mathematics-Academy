import test from "node:test";
import assert from "node:assert/strict";
import { rankedEnglishVoices, selectEnglishVoice } from "../lib/speech-voices.ts";

const makeVoice = (voiceURI, name, lang, isDefault = false) => ({
  voiceURI, name, lang, default: isDefault, localService: true,
});

test("prefers clear natural English voices without excluding South African voices", () => {
  const voices = [
    makeVoice("espeak", "eSpeak", "en-ZA"),
    makeVoice("french", "French Premium", "fr-FR"),
    makeVoice("natural", "Microsoft Sonia Natural", "en-GB"),
    makeVoice("local", "South African English", "en-ZA"),
  ];
  const sorted = rankedEnglishVoices(voices);
  assert.deepEqual(sorted.map((v) => v.voiceURI), ["natural", "local", "espeak"]);
  assert.equal(selectEnglishVoice(voices)?.voiceURI, "natural");
});

test("honours a user's English voice selection and falls back safely", () => {
  const voices = [
    makeVoice("za", "South African English", "en-ZA"),
    makeVoice("uk", "British English", "en-GB"),
    makeVoice("de", "Deutsch", "de-DE"),
  ];
  assert.equal(selectEnglishVoice(voices, "uk")?.voiceURI, "uk");
  assert.equal(selectEnglishVoice(voices, "de")?.voiceURI, "za");
  assert.equal(selectEnglishVoice([], "missing"), null);
});

test("supports browser language spellings using underscore or hyphen", () => {
  const voice = makeVoice("za", "English SA", "en_ZA");
  assert.equal(selectEnglishVoice([voice])?.voiceURI, "za");
});
