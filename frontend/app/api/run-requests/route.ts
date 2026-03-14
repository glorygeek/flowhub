import { NextRequest } from "next/server";

import { proxyFlowHub } from "../_flowhub";

export async function POST(request: NextRequest) {
  return proxyFlowHub(request, "/run-requests/");
}
