"use strict";

/**
 * Compatibility adapter for the fast-glob micromatch entry points.
 *
 * The upstream micromatch 4.0.8 depends on braces 3.0.3, which has
 * GHSA-vfj7-8cjw-p6xm and no upstream patched release. Picomatch handles
 * scanning and matching without braces; @isaacs/brace-expansion 5.0.1
 * performs bounded brace expansion for fast-glob's .braces(...,{expand:true}).
 *
 * Do not silently emulate unsupported compilation semantics. Remove this
 * adapter once the upstream dependency chain has a patched release.
 */
const picomatch = require("picomatch");
const { expand } = require("@isaacs/brace-expansion");
const MAX_PATTERN_LENGTH = 8192;
const MAX_EXPANSIONS = 2048;

function safeBraces(patterns, options = {}) {
  if (options.expand !== true) {
    throw new TypeError("Amaris safe brace adapter supports only bounded expansion");
  }
  const entries = Array.isArray(patterns) ? patterns : [patterns];
  const output = [];
  for (const pattern of entries) {
    if (typeof pattern !== "string" || pattern.length > MAX_PATTERN_LENGTH) {
      throw new RangeError("Glob brace pattern must be a bounded string");
    }
    let depth = 0;
    for (let i = 0; i < pattern.length; i++) {
      if (pattern[i] === "\\") { i++; continue; }
      if (pattern[i] === "{") depth++;
      if (pattern[i] === "}") depth--;
      if (depth > 64) throw new RangeError("Glob brace nesting exceeds safe limit");
    }
    const remaining = MAX_EXPANSIONS - output.length;
    if (remaining <= 0) throw new RangeError("Too many glob brace expansions");
    const values = expand(pattern, { max: remaining });
    if (values.length > remaining) throw new RangeError("Too many glob brace expansions");
    output.push(...values);
  }
  return output;
}

function micromatch(inputs, patterns, options = {}) {
  const files = Array.isArray(inputs) ? inputs : [inputs];
  const globs = Array.isArray(patterns) ? patterns : [patterns];
  return files.filter(file => globs.some(glob => picomatch.isMatch(file, glob, options)));
}

Object.assign(micromatch, picomatch, {
  braces: safeBraces,
  matcher: (pattern, options) => picomatch(pattern, options),
});
module.exports = micromatch;
