import { task } from "@trigger.dev/sdk";

/** Safe development smoke test: no credentials, infrastructure writes, or external calls. */
export const amarisDevelopmentHeartbeat = task({
  id: "amaris-development-heartbeat",
  run: async (payload: { message?: string } = {}) => {
    return {
      project: "Amaris Mathematics Academy",
      message: payload.message ?? "Trigger.dev development task running",
      status: "ok",
      timestamp: new Date().toISOString(),
    };
  },
});
