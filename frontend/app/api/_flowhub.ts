import { NextRequest, NextResponse } from "next/server";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api/v1";
const DEFAULT_API_KEY = "dev-flowhub-key";

function getFlowHubConfig() {
  return {
    apiBaseUrl: (process.env.FLOWHUB_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, ""),
    apiKey: process.env.FLOWHUB_API_KEY || DEFAULT_API_KEY
  };
}

export async function proxyFlowHub(request: NextRequest, backendPath: string) {
  const { apiBaseUrl, apiKey } = getFlowHubConfig();
  const targetUrl = `${apiBaseUrl}${backendPath}${request.nextUrl.search}`;
  const headers = new Headers({
    "X-API-Key": apiKey
  });
  const accept = request.headers.get("accept");
  const contentType = request.headers.get("content-type");

  if (accept) {
    headers.set("Accept", accept);
  }
  if (contentType) {
    headers.set("Content-Type", contentType);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store"
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  const response = await fetch(targetUrl, init);
  const body = await response.text();

  return new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/json"
    }
  });
}
