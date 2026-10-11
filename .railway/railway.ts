// Railway project for one copy of the template. Apply with the Railway CLI:
// `railway config plan`, then `railway config apply`. See docs/guides/deploy.md.
// Railway deletes every resource that this file omits. Add the bucket here
// when its unit exists.
import {
  defineRailway,
  github,
  postgres,
  preserve,
  project,
  redis,
  service,
} from "railway/iac";

// A copy changes these two values. The project name is the repository name.
const REPO = "gunduzhuseyn/seamflow-takehome";
const NAME = "seamflow-takehome";

// The frontend Worker URL. WORKERS_SUBDOMAIN is the account's workers.dev
// subdomain, the same for every copy.
const WORKERS_SUBDOMAIN = "gunduzhuseyn";
const FRONTEND_URL = `https://${NAME}.${WORKERS_SUBDOMAIN}.workers.dev`;

// The Dockerfile CMD listens on this port.
const API_PORT = 8000;

export default defineRailway(() => {
  const db = postgres("Postgres");
  const cache = redis("Redis");

  const api = service("api", {
    // checkSuites is "Wait for CI": deploy only after the GitHub workflow passes.
    // Railway builds backend/Dockerfile because it exists. Railway ignores a
    // builder setting from this file, so the file sets none.
    source: github(REPO, { rootDirectory: "/backend", checkSuites: true }),
    // A push that changes neither path does not deploy the API.
    build: { watchPatterns: ["/backend/**", "/.railway/**"] },
    // Migrate, then run the idempotent seed. `sh -c` runs both in one shell.
    preDeploy: "sh -c 'alembic upgrade head && python -m app.seed'",
    healthcheck: "/health",
    healthcheckTimeout: 60,
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 3 },
    networking: {
      serviceDomains: { [`${NAME}-api.up.railway.app`]: { port: API_PORT } },
    },
    env: {
      ENVIRONMENT: "production",
      PORT: String(API_PORT),
      // SQLAlchemy needs the asyncpg driver in the scheme. Railway resolves the
      // references at deploy time. The host is the private network address.
      DATABASE_URL:
        "postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}" +
        "@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}",
      REDIS_URL: cache.env.REDIS_URL,
      CORS_ORIGINS: FRONTEND_URL,
      // Secrets. Set them with `railway variable set`; see docs/guides/deploy.md.
      // preserve() keeps the value on the service. Without it, apply deletes
      // every variable that this file omits.
      CLERK_SECRET_KEY: preserve(),
      SEED_USER_EMAIL: preserve(),
      SEED_USER_PASSWORD: preserve(),
      ANTHROPIC_API_KEY: preserve(),
    },
  });

  // The arq worker: the same image as api, another start command. No domain
  // and no healthcheck, because nothing connects to it. Its variables are
  // references to api, so a secret is set once.
  const worker = service("worker", {
    source: github(REPO, { rootDirectory: "/backend", checkSuites: true }),
    build: { watchPatterns: ["/backend/**", "/.railway/**"] },
    startCommand: "arq app.worker.WorkerSettings",
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 3 },
    env: {
      ENVIRONMENT: api.env.ENVIRONMENT,
      DATABASE_URL: api.env.DATABASE_URL,
      REDIS_URL: api.env.REDIS_URL,
      // Settings requires every API variable, so the worker references them too.
      CORS_ORIGINS: api.env.CORS_ORIGINS,
      CLERK_SECRET_KEY: api.env.CLERK_SECRET_KEY,
      SEED_USER_EMAIL: api.env.SEED_USER_EMAIL,
      SEED_USER_PASSWORD: api.env.SEED_USER_PASSWORD,
      ANTHROPIC_API_KEY: api.env.ANTHROPIC_API_KEY,
    },
  });

  return project(NAME, { resources: [db, cache, api, worker] });
});
