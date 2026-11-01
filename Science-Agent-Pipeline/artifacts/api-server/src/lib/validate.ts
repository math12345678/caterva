import type { Request, Response, NextFunction } from "express";
import { ZodSchema, ZodError } from "zod";

type ValidationTarget = "body" | "query" | "params";

export function validate(schema: ZodSchema, target: ValidationTarget = "body") {
  return (req: Request, res: Response, next: NextFunction): void => {
    const parse = schema.safeParse(req[target]);
    if (!parse.success) {
      const messages = (parse.error as ZodError).errors.map(
        (e) => `${e.path.join(".")}: ${e.message}`,
      );
      res.status(400).json({
        error: "BAD_REQUEST",
        message: messages.join("; "),
      });
      return;
    }
    req[target] = parse.data;
    next();
  };
}
