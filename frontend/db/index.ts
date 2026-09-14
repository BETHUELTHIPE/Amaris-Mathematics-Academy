import { env } from "cloudflare:workers";
import { drizzle } from "drizzle-orm/d1";
import * as schema from "./schema";

interface AmarisBindings {
  DB: D1Database;
}

const bindings = env as unknown as AmarisBindings;

export function getDb() {
  return drizzle(getD1(), { schema });
}

export function getD1() {
  if (!bindings.DB) {
    throw new Error(
      "Cloudflare D1 binding `DB` is unavailable. Set the `d1` field in .openai/hosting.json to `DB` or let your control plane inject the real binding values before using the database."
    );
  }

  return bindings.DB;
}
