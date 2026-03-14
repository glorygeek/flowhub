import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

let cachedDotEnvValues: Record<string, string> | null = null;

export function loadDotEnvValues(): Record<string, string> {
  if (cachedDotEnvValues) {
    return cachedDotEnvValues;
  }

  const merged: Record<string, string> = {};
  for (const filePath of [resolve(process.cwd(), ".env"), resolve(process.cwd(), "../backend/.env")]) {
    if (!existsSync(filePath)) {
      continue;
    }
    const raw = readFileSync(filePath, "utf-8");
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) {
        continue;
      }
      const [key, ...rest] = trimmed.split("=");
      const value = rest.join("=").trim();
      if (!key.trim()) {
        continue;
      }
      merged[key.trim()] = value;
    }
  }
  cachedDotEnvValues = merged;
  return merged;
}

export function resolveEnvValue(name: string): string {
  const direct = process.env[name];
  if (typeof direct === "string" && direct.trim()) {
    return direct.trim();
  }
  const fromFiles = loadDotEnvValues()[name];
  if (typeof fromFiles === "string" && fromFiles.trim()) {
    return fromFiles.trim();
  }
  return "";
}

export function envFlag(name: string, fallback = false): boolean {
  const raw = String(resolveEnvValue(name) ?? "").trim().toLowerCase();
  if (!raw) {
    return fallback;
  }
  return raw === "1" || raw === "true" || raw === "yes" || raw === "on";
}

export function envList(name: string, fallback: string[] = []): string[] {
  const raw = String(resolveEnvValue(name) ?? "").trim();
  if (!raw) {
    return fallback;
  }
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
