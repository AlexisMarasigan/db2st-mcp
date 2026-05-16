// k6 load test for db2st-mcp.
//
// Usage:
//   DB2ST_URL=http://localhost:8080 DB2ST_TOKEN=<bearer> k6 run scripts/loadtest.k6.js
//
// Target: p95 < 800ms at 100 RPS sustained for 1 minute.

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.DB2ST_URL || 'http://localhost:8080';
const TOKEN = __ENV.DB2ST_TOKEN || '';

const REFS = [
  '1806203236', '1806290829', '1806273700', '1806272330',
  '1806271886', '1806270433', '1806268072', '1806267579',
  '1806264568', '1806258974', '1806256390',
];

export const options = {
  scenarios: {
    sustained: {
      executor: 'constant-arrival-rate',
      rate: 100,
      timeUnit: '1s',
      duration: '1m',
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<800'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const ref = REFS[Math.floor(Math.random() * REFS.length)];
  // 50/50 between the two registered MCP tools so the load profile
  // matches a realistic mix of "full shipment" vs "events timeline only"
  // callers. Both go through the same TrackingService orchestrator, so
  // p95 should track upstream + cache + breaker behaviour either way.
  const toolName =
    Math.random() < 0.5 ? 'track_shipment' : 'track_shipment_events';
  const body = JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    method: 'tools/call',
    params: { name: toolName, arguments: { reference: ref } },
  });
  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json, text/event-stream',
  };
  if (TOKEN) headers['Authorization'] = `Bearer ${TOKEN}`;

  const res = http.post(`${BASE}/mcp/`, body, { headers });
  check(res, {
    'status 200': (r) => r.status === 200,
    'no auth error': (r) => r.status !== 401,
    'no quota error': (r) => r.status !== 429,
  });
  sleep(0.1);
}
