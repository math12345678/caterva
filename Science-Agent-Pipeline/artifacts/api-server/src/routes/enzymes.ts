import {
  Router,
  type IRouter,
  type Request,
  type Response,
  type NextFunction,
} from "express";
import { ENZYMES } from "../lib/enzymes";
import {
  RequiredParametersMissingError,
  UnrecognizedQueryError,
} from "../lib/provenance";
import { logger } from "../lib/logger";
import { validate } from "../lib/validate";
import { ResolveBody } from "../lib/schemas";

const router: IRouter = Router();

router.get("/enzymes", (_req: Request, res: Response) => {
  res.json(
    ENZYMES.map((e) => ({
      ecNumber: e.ecNumber,
      name: e.enzymeName,
      substrates: e.substrates,
      description: e.description,
      organism: e.organism,
    })),
  );
});

router.post(
  "/resolve",
  validate(ResolveBody),
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { query } = req.body as { query: string };
      logger.info({ query }, "Resolving query for preview");
      // queryResolver pulls in the whole resolution graph (LLM resolver,
      // science agent, citation helpers). It is only needed once a resolve
      // request arrives, so load it here rather than at route registration.
      const { resolveQuery } = await import("../lib/queryResolver");
      const resolved = await resolveQuery(query);

      res.json({
        domain: resolved.domain,
        parameters: resolved.parameters,
        provenance: {
          reasoning: resolved.provenance.reasoning,
          modelCitations: resolved.provenance.modelCitations,
          flags: resolved.provenance.flags,
        },
        parameterProvenance: resolved.parameterProvenance,
      });
    } catch (err) {
      if (err instanceof RequiredParametersMissingError) {
        // `domain` was already on the error object (`err.domain`) and
        // simply never left the process: a caller could see WHICH keys
        // were missing but not which domain's parameter shape to render a
        // form for, so the only thing the landing page's agent UI could
        // do with a 422 was print the prose message and stop -- even
        // though it already has a labeled-field form for every domain
        // (`DOMAIN_PARAMS`) sitting unreachable behind this gap. Purely
        // additive: no existing consumer reads a field that was not
        // there before.
        res.status(422).json({
          error: "RequiredParametersMissingError",
          message: err.message,
          missingKeys: err.missing,
          domain: err.domain,
          // Whatever resolved before the refusal -- a literature Km, or a
          // value the caller already typed inline. Lets a form pre-fill
          // what succeeded instead of making the user retype it just to
          // supply the one thing that was actually missing.
          resolvedParameters: err.resolvedSoFar,
          // WHY each missing key is missing, per key, and WHERE each
          // resolved value came from. The landing page used to show only
          // its own paraphrase ("vmax is yours to choose") -- the opposite
          // of what `details.vmax` says (Vmax = kcat x [E]0: state the
          // enzyme concentration and it is derived and cited) -- because
          // `message` was the one explanation it could read, and it did
          // not read that either. `parameterProvenance` lets the form keep
          // a resolved Km's citation instead of re-sending the number as
          // if the person had typed it.
          details: err.details,
          parameterProvenance: err.parameterProvenance,
          // "assumed: organism = Homo sapiens ..." and the like: the
          // choices made for the person, which a 422 dropped although the
          // resolved Km beside them was made under one (provenance.ts).
          flags: err.flags,
        });
        return;
      }
      if (err instanceof UnrecognizedQueryError) {
        // Distinct from RequiredParametersMissingError: this query never
        // matched a domain at all, so there is no `domain`/parameter shape
        // to render a form for -- only a list of what IS supported, so the
        // UI can suggest rephrasing or picking one directly.
        res.status(422).json({
          error: "UnrecognizedQueryError",
          message: err.message,
          availableDomains: err.availableDomains,
        });
        return;
      }
      next(err);
    }
  },
);

export default router;
