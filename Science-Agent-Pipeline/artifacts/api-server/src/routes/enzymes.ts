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
        res.status(400).json({
          error: "MISSING_REQUIRED_INPUT",
          message: err.message,
          domain: err.domain,
          missing: err.missing,
        });
        return;
      }
      next(err);
    }
  },
);

export default router;
