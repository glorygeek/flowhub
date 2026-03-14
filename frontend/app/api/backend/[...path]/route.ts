import { NextRequest } from "next/server";

import { proxyFlowHub } from "../../_flowhub";

function getBackendPath(request: NextRequest) {
  return request.nextUrl.pathname.replace(/^\/api\/backend/, "") || "/";
}

async function handle(request: NextRequest) {
  return proxyFlowHub(request, getBackendPath(request));
}

export async function GET(request: NextRequest) {
  return handle(request);
}

export async function POST(request: NextRequest) {
  return handle(request);
}

export async function PUT(request: NextRequest) {
  return handle(request);
}

export async function PATCH(request: NextRequest) {
  return handle(request);
}

export async function DELETE(request: NextRequest) {
  return handle(request);
}

export async function OPTIONS(request: NextRequest) {
  return handle(request);
}
