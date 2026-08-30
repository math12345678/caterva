import {
  Router,
  type IRouter,
  type Request,
  type Response,
  type NextFunction,
} from "express";
import { ENZYMES } from "../lib/enzymes";
import { resolveQuery } from "../lib/queryResolver";
import { RequiredParametersMissingError } from "../lib/provenance";
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
        });
        return;
      }
      next(err);
    }
  },
);

export default router;
