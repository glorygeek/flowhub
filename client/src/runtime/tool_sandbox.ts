import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { basename, delimiter, extname, isAbsolute, relative, resolve } from "node:path";

import type {
  ClientToolManifestEntry,
  ClientToolSandboxConfig,
  ExternalToolHttpRequest,
  ExternalToolRequest,
  ExternalToolShellCommand
} from "../types";
import { envFlag, envList, resolveEnvValue } from "./runtime_env";

const DEFAULT_ALLOWED_HOSTS = ["clawhub.ai", "localhost", "127.0.0.1", "::1"];
const DEFAULT_ALLOWED_METHODS = ["GET", "POST"];
const SENSITIVE_HEADER_NAMES = new Set(["authorization", "cookie", "x-api-key", "proxy-authorization"]);

function isLocalHost(hostname: string): boolean {
  return ["localhost", "127.0.0.1", "::1"].includes(hostname);
}

function normalizeHeaderMap(headers: Record<string, unknown> | undefined): Record<string, string> {
  const output: Record<string, string> = {};
  if (!headers || typeof headers !== "object") {
    return output;
  }
  for (const [key, value] of Object.entries(headers)) {
    if (typeof value === "string" && key.trim()) {
      output[key.trim()] = value;
    }
  }
  return output;
}

function isAllowedHost(hostname: string, allowedHosts: string[]): boolean {
  const normalized = hostname.trim().toLowerCase();
  return allowedHosts.some((entry) => {
    const candidate = entry.trim().toLowerCase();
    if (!candidate) {
      return false;
    }
    if (candidate.startsWith(".")) {
      return normalized.endsWith(candidate);
    }
    return normalized === candidate;
  });
}

export function resolveClientToolSandbox(): ClientToolSandboxConfig {
  return {
    enabled: envFlag("CLIENT_TOOL_SANDBOX_ENABLED", true),
    allowed_hosts: envList("CLIENT_TOOL_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS),
    allowed_methods: envList("CLIENT_TOOL_ALLOWED_METHODS", DEFAULT_ALLOWED_METHODS).map((item) =>
      item.toUpperCase()
    ),
    allowed_commands: envList("CLIENT_TOOL_ALLOWED_COMMANDS"),
    manifest_path: resolveEnvValue("CLIENT_TOOL_MANIFEST_PATH") || "./tool-manifest.json",
    manifest_required: envFlag("CLIENT_TOOL_MANIFEST_REQUIRED", false),
    manifest_require_release_metadata: envFlag("CLIENT_TOOL_MANIFEST_REQUIRE_METADATA", true),
    manifest_allowed_signers: envList("CLIENT_TOOL_MANIFEST_ALLOWED_SIGNERS"),
    manifest_allowed_fingerprints: envList("CLIENT_TOOL_MANIFEST_ALLOWED_FINGERPRINTS"),
    manifest_allowed_release_batches: envList("CLIENT_TOOL_MANIFEST_ALLOWED_RELEASE_BATCHES"),
    manifest_current_release_batch: resolveEnvValue("CLIENT_TOOL_MANIFEST_CURRENT_RELEASE_BATCH") || "",
    manifest_previous_release_batches: envList("CLIENT_TOOL_MANIFEST_PREVIOUS_RELEASE_BATCHES"),
    manifest_previous_batch_grace_days: Number(
      resolveEnvValue("CLIENT_TOOL_MANIFEST_PREVIOUS_BATCH_GRACE_DAYS") || 30
    ),
    manifest_enforce_expiration: envFlag("CLIENT_TOOL_MANIFEST_ENFORCE_EXPIRATION", true),
    manifest_require_revocation_audit: envFlag("CLIENT_TOOL_MANIFEST_REQUIRE_REVOCATION_AUDIT", true),
    allow_sensitive_headers: envFlag("CLIENT_TOOL_ALLOW_SENSITIVE_HEADERS", false),
    timeout_seconds: Number(resolveEnvValue("CLIENT_TOOL_TIMEOUT_SECONDS") || 20),
    max_response_bytes: Number(resolveEnvValue("CLIENT_TOOL_MAX_RESPONSE_BYTES") || 32768)
  };
}

export function parseExternalToolRequest(value: unknown): ExternalToolRequest | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const kind = String(raw.kind || "").trim();
  if (kind === "http_request") {
    const url = String(raw.url || "").trim();
    if (!url) {
      throw new Error("external_tool.url is required for http_request");
    }
    return {
      kind: "http_request",
      method: String(raw.method || "GET").trim().toUpperCase() as ExternalToolHttpRequest["method"],
      url,
      headers: normalizeHeaderMap(raw.headers as Record<string, unknown> | undefined),
      body: raw.body,
      timeout_seconds: typeof raw.timeout_seconds === "number" ? raw.timeout_seconds : undefined,
      response_format:
        raw.response_format === "json" || raw.response_format === "text"
          ? raw.response_format
          : undefined
    };
  }
  if (kind === "shell_command") {
    const command = String(raw.command || "").trim();
    if (!command) {
      throw new Error("external_tool.command is required for shell_command");
    }
    return {
      kind: "shell_command",
      command,
      args: Array.isArray(raw.args) ? raw.args.filter((item): item is string => typeof item === "string") : [],
      cwd: typeof raw.cwd === "string" ? raw.cwd : undefined,
      timeout_seconds: typeof raw.timeout_seconds === "number" ? raw.timeout_seconds : undefined
    };
  }
  throw new Error(`Unsupported external tool kind: ${kind || "unknown"}`);
}

export function validateSandboxedHttpRequest(
  request: Pick<ExternalToolHttpRequest, "method" | "url" | "headers">,
  config: ClientToolSandboxConfig
): URL {
  if (!config.enabled) {
    return new URL(request.url);
  }

  const parsed = new URL(request.url);
  if (!isAllowedHost(parsed.hostname, config.allowed_hosts)) {
    throw new Error(`Sandbox denied host: ${parsed.hostname}`);
  }
  if (!config.allowed_methods.includes(request.method.toUpperCase())) {
    throw new Error(`Sandbox denied HTTP method: ${request.method}`);
  }
  if (parsed.protocol !== "https:" && !(parsed.protocol === "http:" && isLocalHost(parsed.hostname))) {
    throw new Error(`Sandbox denied insecure protocol for host: ${parsed.hostname}`);
  }
  for (const headerName of Object.keys(request.headers || {})) {
    if (!config.allow_sensitive_headers && SENSITIVE_HEADER_NAMES.has(headerName.trim().toLowerCase())) {
      throw new Error(`Sandbox denied sensitive header: ${headerName}`);
    }
  }
  return parsed;
}

export async function executeSandboxedHttpRequest(
  request: ExternalToolHttpRequest,
  config: ClientToolSandboxConfig
): Promise<Record<string, unknown>> {
  const parsedUrl = validateSandboxedHttpRequest(request, config);
  const timeoutMs = Math.max(1000, (request.timeout_seconds || config.timeout_seconds) * 1000);
  const response = await fetch(parsedUrl, {
    method: request.method,
    headers: request.headers,
    body:
      typeof request.body === "undefined" || request.body === null
        ? undefined
        : typeof request.body === "string"
          ? request.body
          : JSON.stringify(request.body),
    signal: AbortSignal.timeout(timeoutMs)
  });
  const responseText = await response.text();
  if (Buffer.byteLength(responseText, "utf-8") > config.max_response_bytes) {
    throw new Error(`Sandbox denied oversized response from ${parsedUrl.hostname}`);
  }

  let parsedBody: unknown = responseText;
  const responseFormat = request.response_format;
  const contentType = response.headers.get("content-type") || "";
  if (responseFormat === "json" || contentType.includes("application/json")) {
    try {
      parsedBody = responseText ? JSON.parse(responseText) : null;
    } catch {
      parsedBody = responseText;
    }
  }

  if (!response.ok) {
    throw new Error(`External HTTP tool ${response.status}: ${responseText}`);
  }

  return {
    runtime: "external_tool",
    tool_kind: "http_request",
    method: request.method,
    url: parsedUrl.toString(),
    status_code: response.status,
    response_headers: Object.fromEntries(response.headers.entries()),
    response:
      typeof parsedBody === "string"
        ? parsedBody
        : parsedBody ?? null
  };
}

function validateShellCommand(request: ExternalToolShellCommand, config: ClientToolSandboxConfig): string {
  if (!config.enabled) {
    return request.command;
  }
  const commandName = basename(request.command);
  if (!config.allowed_commands.includes(commandName)) {
    throw new Error(`Sandbox denied shell command: ${commandName}`);
  }
  return request.command;
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function parseManifestIsoDate(value: string, label: string, commandName: string): Date {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error(`Sandbox manifest invalid ${label} for command: ${commandName}`);
  }
  return parsed;
}

async function loadToolManifest(config: ClientToolSandboxConfig): Promise<ClientToolManifestEntry[]> {
  try {
    const raw = await readFile(resolve(process.cwd(), config.manifest_path), "utf-8");
    const parsed = JSON.parse(raw) as { tools?: ClientToolManifestEntry[] } | ClientToolManifestEntry[];
    const items = Array.isArray(parsed) ? parsed : parsed.tools;
    if (!Array.isArray(items)) {
      return [];
    }
    return items.filter(
      (item): item is ClientToolManifestEntry =>
        Boolean(item && isNonEmptyString(item.command) && isNonEmptyString(item.path) && isNonEmptyString(item.sha256))
    );
  } catch {
    return [];
  }
}

async function computeFileSha256(filePath: string): Promise<string> {
  const content = await readFile(filePath);
  return createHash("sha256").update(content).digest("hex");
}

function pathCandidatesForCommand(command: string): string[] {
  if (command.includes("/") || command.includes("\\") || isAbsolute(command)) {
    return [resolve(process.cwd(), command)];
  }

  const pathDirs = String(process.env.PATH || "")
    .split(delimiter)
    .map((item) => item.trim())
    .filter(Boolean);
  const pathext =
    process.platform === "win32"
      ? String(process.env.PATHEXT || ".EXE;.CMD;.BAT;.COM")
          .split(";")
          .map((item) => item.trim().toLowerCase())
          .filter(Boolean)
      : [""];

  const candidates: string[] = [];
  for (const dir of pathDirs) {
    const base = resolve(dir, command);
    candidates.push(base);
    if (!extname(base) && process.platform === "win32") {
      for (const extension of pathext) {
        candidates.push(`${base}${extension}`);
      }
    }
  }
  return candidates;
}

async function resolveManifestBoundCommand(
  request: ExternalToolShellCommand,
  config: ClientToolSandboxConfig
): Promise<{ command_path: string; manifest_entry: ClientToolManifestEntry | null }> {
  const commandName = basename(request.command);
  const manifest = await loadToolManifest(config);
  const manifestEntry = manifest.find((item) => item.command === commandName);

  if (!manifestEntry) {
    if (config.manifest_required) {
      throw new Error(`Sandbox manifest denied shell command: ${commandName}`);
    }
    return {
      command_path: validateShellCommand(request, config),
      manifest_entry: null
    };
  }

  if (manifestEntry.revoked) {
    if (config.manifest_require_revocation_audit) {
      if (!isNonEmptyString(manifestEntry.revoked_by)) {
        throw new Error(`Sandbox manifest missing revoked_by metadata for command: ${commandName}`);
      }
      if (!isNonEmptyString(manifestEntry.revocation_ticket)) {
        throw new Error(`Sandbox manifest missing revocation_ticket metadata for command: ${commandName}`);
      }
    }
    throw new Error(
      manifestEntry.revocation_reason
        ? `Sandbox manifest revoked shell command: ${commandName} (${manifestEntry.revocation_reason})`
        : `Sandbox manifest revoked shell command: ${commandName}`
    );
  }
  if (config.manifest_require_release_metadata) {
    if (!isNonEmptyString(manifestEntry.version)) {
      throw new Error(`Sandbox manifest missing version metadata for command: ${commandName}`);
    }
    if (!isNonEmptyString(manifestEntry.signer)) {
      throw new Error(`Sandbox manifest missing signer metadata for command: ${commandName}`);
    }
    if (!isNonEmptyString(manifestEntry.published_at)) {
      throw new Error(`Sandbox manifest missing published_at metadata for command: ${commandName}`);
    }
  }
  if (config.manifest_allowed_signers.length > 0) {
    if (!isNonEmptyString(manifestEntry.signer)) {
      throw new Error(`Sandbox manifest missing signer metadata for command: ${commandName}`);
    }
    const allowed = new Set(config.manifest_allowed_signers.map((item) => item.trim()).filter(Boolean));
    if (!allowed.has(manifestEntry.signer.trim())) {
      throw new Error(`Sandbox manifest denied signer for command: ${commandName}`);
    }
  }
  if (config.manifest_allowed_fingerprints.length > 0) {
    if (!isNonEmptyString(manifestEntry.signer_fingerprint)) {
      throw new Error(`Sandbox manifest missing signer_fingerprint metadata for command: ${commandName}`);
    }
    const allowedFingerprints = new Set(
      config.manifest_allowed_fingerprints.map((item) => item.trim()).filter(Boolean)
    );
    if (!allowedFingerprints.has(manifestEntry.signer_fingerprint.trim())) {
      throw new Error(`Sandbox manifest denied signer fingerprint for command: ${commandName}`);
    }
  }
  if (config.manifest_allowed_release_batches.length > 0) {
    if (!isNonEmptyString(manifestEntry.release_batch)) {
      throw new Error(`Sandbox manifest missing release_batch metadata for command: ${commandName}`);
    }
    const allowedBatches = new Set(
      config.manifest_allowed_release_batches.map((item) => item.trim()).filter(Boolean)
    );
    if (!allowedBatches.has(manifestEntry.release_batch.trim())) {
      throw new Error(`Sandbox manifest denied release batch for command: ${commandName}`);
    }
  }
  if (config.manifest_current_release_batch.trim()) {
    if (!isNonEmptyString(manifestEntry.release_batch)) {
      throw new Error(`Sandbox manifest missing release_batch metadata for command: ${commandName}`);
    }
    const currentBatch = config.manifest_current_release_batch.trim();
    const previousBatches = new Set(
      config.manifest_previous_release_batches.map((item) => item.trim()).filter(Boolean)
    );
    const releaseBatch = manifestEntry.release_batch.trim();
    if (releaseBatch !== currentBatch) {
      if (!previousBatches.has(releaseBatch)) {
        throw new Error(`Sandbox manifest denied release batch for command: ${commandName}`);
      }
      if (!isNonEmptyString(manifestEntry.published_at)) {
        throw new Error(`Sandbox manifest missing published_at metadata for command: ${commandName}`);
      }
      const publishedAt = parseManifestIsoDate(manifestEntry.published_at, "published_at", commandName);
      const graceMs = Math.max(0, config.manifest_previous_batch_grace_days) * 24 * 60 * 60 * 1000;
      if (publishedAt.getTime() < Date.now() - graceMs) {
        throw new Error(`Sandbox manifest previous release batch expired for command: ${commandName}`);
      }
    }
  }
  if (isNonEmptyString(manifestEntry.published_at)) {
    parseManifestIsoDate(manifestEntry.published_at, "published_at", commandName);
  }
  if (config.manifest_enforce_expiration) {
    if (!isNonEmptyString(manifestEntry.expires_at)) {
      throw new Error(`Sandbox manifest missing expires_at metadata for command: ${commandName}`);
    }
    const expiresAt = parseManifestIsoDate(manifestEntry.expires_at, "expires_at", commandName);
    if (expiresAt.getTime() <= Date.now()) {
      throw new Error(`Sandbox manifest expired shell command: ${commandName}`);
    }
  }

  const manifestPath = resolve(process.cwd(), manifestEntry.path);
  const requestedCandidates = pathCandidatesForCommand(request.command);
  if (
    requestedCandidates.length > 0 &&
    !requestedCandidates.some((item) => resolve(item) === manifestPath)
  ) {
    throw new Error(`Sandbox manifest path mismatch for command: ${commandName}`);
  }

  const digest = await computeFileSha256(manifestPath);
  if (digest.toLowerCase() !== manifestEntry.sha256.trim().toLowerCase()) {
    throw new Error(`Sandbox manifest hash mismatch for command: ${commandName}`);
  }

  return {
    command_path: manifestPath,
    manifest_entry: manifestEntry
  };
}

function resolveShellCwd(request: ExternalToolShellCommand): string {
  const cwd = request.cwd ? resolve(process.cwd(), request.cwd) : process.cwd();
  const root = resolve(process.cwd());
  const rel = relative(root, cwd);
  if (rel.startsWith("..") || rel === "") {
    if (rel === "") {
      return cwd;
    }
    throw new Error("Sandbox denied cwd outside client workspace");
  }
  return cwd;
}

function isWindowsBatchFile(command: string): boolean {
  if (process.platform !== "win32") {
    return false;
  }
  const extension = extname(command).toLowerCase();
  return extension === ".cmd" || extension === ".bat";
}

function quoteWindowsBatchArg(value: string): string {
  if (/[\r\n]/.test(value)) {
    throw new Error("Sandbox denied multiline shell argument");
  }
  if (/[&|<>^%!]/.test(value)) {
    throw new Error("Sandbox denied unsafe shell metacharacters in argument");
  }
  return `"${value.replace(/"/g, "\"\"")}"`;
}

export async function executeSandboxedShellCommand(
  request: ExternalToolShellCommand,
  config: ClientToolSandboxConfig
): Promise<Record<string, unknown>> {
  const resolvedCommand = await resolveManifestBoundCommand(request, config);
  const command = resolvedCommand.command_path;
  const cwd = resolveShellCwd(request);
  const timeoutMs = Math.max(1000, (request.timeout_seconds || config.timeout_seconds) * 1000);
  const useWindowsShell = isWindowsBatchFile(command);
  const spawnCommand = useWindowsShell
    ? [quoteWindowsBatchArg(command), ...request.args.map(quoteWindowsBatchArg)].join(" ")
    : command;
  const spawnArgs = useWindowsShell ? [] : request.args;

  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(spawnCommand, spawnArgs, {
      cwd,
      env: { PATH: process.env.PATH || "" },
      stdio: ["ignore", "pipe", "pipe"],
      shell: useWindowsShell
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      if (!settled) {
        settled = true;
        rejectPromise(new Error(`Sandbox command timeout after ${timeoutMs}ms`));
      }
    }, timeoutMs);

    const trimBuffered = (value: string) => {
      const maxBytes = config.max_response_bytes;
      if (Buffer.byteLength(value, "utf-8") <= maxBytes) {
        return value;
      }
      return value.slice(value.length - Math.floor(maxBytes / 2));
    };

    child.stdout.on("data", (chunk) => {
      stdout = trimBuffered(stdout + String(chunk));
    });
    child.stderr.on("data", (chunk) => {
      stderr = trimBuffered(stderr + String(chunk));
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      if (!settled) {
        settled = true;
        rejectPromise(error);
      }
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (settled) {
        return;
      }
      if (code !== 0) {
        settled = true;
        rejectPromise(new Error(`Sandbox command exited with code ${code}: ${stderr}`));
        return;
      }
      settled = true;
      resolvePromise({
        runtime: "external_tool",
        tool_kind: "shell_command",
        command: basename(command),
        args: request.args,
        cwd,
        manifest_path: config.manifest_path,
        manifest_entry: resolvedCommand.manifest_entry
          ? {
              command: resolvedCommand.manifest_entry.command,
              version: resolvedCommand.manifest_entry.version ?? null,
              signer: resolvedCommand.manifest_entry.signer ?? null,
              signer_fingerprint: resolvedCommand.manifest_entry.signer_fingerprint ?? null,
              release_batch: resolvedCommand.manifest_entry.release_batch ?? null,
              published_at: resolvedCommand.manifest_entry.published_at ?? null,
              expires_at: resolvedCommand.manifest_entry.expires_at ?? null,
              revoked: Boolean(resolvedCommand.manifest_entry.revoked),
              revoked_by: resolvedCommand.manifest_entry.revoked_by ?? null,
              revocation_ticket: resolvedCommand.manifest_entry.revocation_ticket ?? null,
              description: resolvedCommand.manifest_entry.description ?? null
            }
          : null,
        stdout,
        stderr
      });
    });
  });
}

export async function executeSandboxedExternalTool(
  request: ExternalToolRequest,
  config: ClientToolSandboxConfig
): Promise<Record<string, unknown>> {
  if (request.kind === "http_request") {
    return executeSandboxedHttpRequest(request, config);
  }
  return executeSandboxedShellCommand(request, config);
}
