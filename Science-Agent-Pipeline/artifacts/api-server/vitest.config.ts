import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: {
    conditions: ["workspace"],
  },
  test: {
    globals: true,
    environment: "node",
    include: ["src/**/*.test.ts"],
    // 15s was a coin flip, not a timeout.
    //
    // Several tests in this suite spawn a Python interpreter and run a real
    // simulation through it. `gillespieBimolecularGolden` takes 11.5s ALONE
    // -- 76% of the old budget -- and under `--shard` contention, with
    // several workers spawning Python at once, the same work took long
    // enough to blow through it. The suite then reported a failed assertion
    // in a golden trajectory test, which reads exactly like a numerical
    // regression and is not one.
    //
    // A test that passes alone and fails in parallel is the worst failure
    // mode a suite has: it teaches people to re-run rather than
    // investigate, and the next real failure gets re-run too.
    //
    // 60s is deliberately generous rather than tuned to the current machine.
    // The purpose of this timeout is to bound a HANG, not to police
    // performance -- performance is what `/api/perf` is for. A budget set
    // close to the observed runtime turns every slow machine into a red
    // build about something that did not change.
    testTimeout: 60000,
    hookTimeout: 30000,
    // Recorded real BRENDA pages replace live fetches for the ECs they
    // cover (Tests/fixtures/recorded/README.md): five hexokinase tests
    // failed three CI runs on BRENDA returning 500, not on a defect.
    //
    // CATERVA_HTTP_RECORDED does the same for every other GET the runner
    // makes through Tests/http_retry.py: NCBI Taxonomy, UniProt and
    // PubChem, which one hexokinase Km lookup asks 15 times and which timed
    // these tests out in CI whenever one of them was slow. A request with
    // no recording still goes live. scripts/record_http_fixtures.py lists
    // the payloads these tests send and re-records them.
    //
    // Test configuration only. The product must never set either variable
    // (Tests/test_recorded_env_is_test_only.py): a recorded answer served
    // to a user would be presented as the database's current one.
    env: {
      CATERVA_BRENDA_RECORDED: path.resolve(__dirname, "../../../Tests/fixtures/recorded"),
      CATERVA_HTTP_RECORDED: path.resolve(__dirname, "../../../Tests/fixtures/recorded/http"),
    },
    clearMocks: true,
    restoreMocks: true,
  },
});
