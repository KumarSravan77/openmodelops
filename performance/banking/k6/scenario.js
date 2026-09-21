import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';
import { Counter } from 'k6/metrics';

const target = __ENV.BANKING_BASE_URL || 'http://banking-api:8000';
const profile = __ENV.LOAD_PROFILE || 'baseline';
const profiles = {
  smoke: { executor: 'constant-arrival-rate', rate: 5, timeUnit: '1s', duration: '30s', preAllocatedVUs: 5, maxVUs: 20 },
  baseline: { executor: 'constant-arrival-rate', rate: 20, timeUnit: '1s', duration: '5m', preAllocatedVUs: 20, maxVUs: 100 },
  load: { executor: 'ramping-arrival-rate', startRate: 20, timeUnit: '1s', preAllocatedVUs: 50, maxVUs: 300, stages: [{ target: 100, duration: '5m' }, { target: 100, duration: '20m' }, { target: 20, duration: '5m' }] },
  spike: { executor: 'ramping-arrival-rate', startRate: 10, timeUnit: '1s', preAllocatedVUs: 50, maxVUs: 500, stages: [{ target: 10, duration: '1m' }, { target: 250, duration: '30s' }, { target: 250, duration: '2m' }, { target: 10, duration: '1m' }] },
  soak: { executor: 'constant-arrival-rate', rate: 40, timeUnit: '1s', duration: '2h', preAllocatedVUs: 50, maxVUs: 200 },
  saturation: { executor: 'constant-vus', vus: 2, duration: '30s' },
};

const responseErrors = new Counter('banking_response_errors');
let errorLogged = false;

export const options = {
  scenarios: { banking: profiles[profile] || profiles.baseline },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<250', 'p(99)<500'],
    checks: ['rate>0.99'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const provinces = ['ON', 'QC', 'BC', 'AB', 'MB', 'SK', 'NS', 'NB'];
const channels = ['card_present', 'ecommerce', 'transfer', 'bill_payment'];

export default function () {
  const sequence = exec.scenario.iterationInTest;
  const suspicious = sequence % 50 === 0;
  const payload = JSON.stringify({
    event_id: `k6-${String(exec.vu.idInTest).padStart(4, '0')}-${String(sequence).padStart(12, '0')}`,
    account_token: `synthetic-${String(exec.vu.idInTest).padStart(12, '0')}`,
    amount_cad: suspicious ? '12500.00' : '82.50',
    province: provinces[sequence % provinces.length],
    channel: channels[sequence % channels.length],
    merchant_category: suspicious ? 'electronics' : 'grocery',
    occurred_at: new Date().toISOString(),
    device_trusted: !suspicious,
    international: suspicious,
    transactions_last_10m: suspicious ? 14 : 2,
    failed_auth_last_24h: suspicious ? 5 : 0,
  });
  const response = http.post(`${target}/v1/transactions/score`, payload, { headers: { 'Content-Type': 'application/json' }, tags: { profile } });
  const success = response.status === 200;
  if (!success) {
    responseErrors.add(1, { status: String(response.status || 'network') });
    if (__ENV.DEBUG_ERRORS === 'true' && !errorLogged) {
      console.error(`status=${response.status} sequence=${sequence} body=${response.body}`);
      errorLogged = true;
    }
  }
  check(response, {
    'HTTP 200': () => success,
    'valid decision': (value) => success && ['approve', 'review', 'decline'].includes(value.json('decision')),
    'model version present': (value) => success && Boolean(value.json('model_version')),
  });
}

export function handleSummary(data) {
  return { '/results/banking-summary.json': JSON.stringify(data, null, 2), stdout: `profile=${profile} p95=${data.metrics.http_req_duration.values['p(95)']}ms\n` };
}
