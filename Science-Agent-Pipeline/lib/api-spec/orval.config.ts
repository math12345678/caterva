import { defineConfig, InputTransformerFn } from "orval";
import path from "path";

const root = path.resolve(__dirname, "..", "..");
const apiClientReactSrc = path.resolve(root, "lib", "api-client-react", "src");
const apiZodSrc = path.resolve(root, "lib", "api-zod", "src");

// Our exports make assumptions about the title of the API being "Api" (i.e. generated output is `api.ts`).
const titleTransformer: InputTransformerFn = (config) => {
  config.info ??= {};
  config.info.title = "Api";

  return config;
};

export default defineConfig({
  "api-client-react": {
    input: {
      target: "./openapi.yaml",
      override: {
        transformer: titleTransformer,
      },
    },
    output: {
      workspace: apiClientReactSrc,
      target: "generated",
      client: "react-query",
      mode: "split",
      baseUrl: "/api",
      clean: true,
      // `prettier: true` -- the key orval used before v8 -- was silently
      // ignored, because unknown keys in a config object are not errors at
      // runtime. So the generated client was never formatted, despite the
      // config saying it was. orval 8 spells it `formatter`
      // (SupportedFormatter: "prettier" | "biome" | "oxfmt"). Caught the
      // first time this file was ever type-checked.
      formatter: "prettier",
      override: {
        fetch: {
          includeHttpResponseReturnType: false,
        },
        mutator: {
          path: path.resolve(apiClientReactSrc, "custom-fetch.ts"),
          name: "customFetch",
        },
      },
    },
  },
  zod: {
    input: {
      target: "./openapi.yaml",
      override: {
        transformer: titleTransformer,
      },
    },
    output: {
      workspace: apiZodSrc,
      client: "zod",
      target: "generated",
      schemas: { path: "generated/types", type: "typescript" },
      mode: "split",
      clean: true,
      // `prettier: true` -- the key orval used before v8 -- was silently
      // ignored, because unknown keys in a config object are not errors at
      // runtime. So the generated client was never formatted, despite the
      // config saying it was. orval 8 spells it `formatter`
      // (SupportedFormatter: "prettier" | "biome" | "oxfmt"). Caught the
      // first time this file was ever type-checked.
      formatter: "prettier",
      override: {
        zod: {
          // PINNED, not left to `auto`.
          //
          // orval's default is `version: "auto"`, which inspects the
          // installed zod. zod 3.25 ships a `zod/v4` SUBPATH, so detection
          // concludes v4 and emits v4 syntax -- `zod.iso.datetime(...)` --
          // while still importing from plain `"zod"`, where `iso` is
          // `undefined`. The generated schema then throws on load.
          //
          // That is not a cosmetic difference. Before this line, running the
          // documented `pnpm --filter @workspace/api-spec run codegen`
          // produced a contract that crashed at import, and the only reason
          // nobody hit it is that the committed files predate the zod bump
          // and nobody had regenerated. ADR 0027 recorded this as a
          // formatting-level drift; it was worse than that.
          //
          // Verified rather than assumed:
          //   node -e "const z=require('zod'); console.log(typeof z.iso)"
          //   -> undefined      (zod 3.25.76)
          //
          // Raise this to 4 in the same commit that moves the workspace to
          // zod@^4, and not before.
          version: 3,
          coerce: {
            query: ["boolean", "number", "string"],
            param: ["boolean", "number", "string"],
            body: ["bigint", "date"],
            response: ["bigint", "date"],
          },
        },
        useDates: true,
        useBigInt: true,
      },
    },
  },
});
