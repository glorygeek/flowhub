import { NextRequest } from "next/server";

import { proxyFlowHub } from "../../../_flowhub";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ requestId: string }> }
) {
  const { requestId } = await context.params;
  return proxyFlowHub(request, `/run-requests/${requestId}/confirm`);
}
