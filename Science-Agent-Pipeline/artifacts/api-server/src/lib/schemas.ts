import { z } from "zod";

export const WaitlistBody = z.object({
  email: z.string().email("Invalid email address").trim().toLowerCase(),
});

export const ResolveBody = z.object({
  query: z
    .string()
    .min(1, "query is required")
    .max(500, "query must be 500 characters or fewer")
    .transform((s) => s.trim()),
});

export const CancelJobParams = z.object({
  jobId: z.coerce.string().min(1),
});

export const ExportJobParams = z.object({
  jobId: z.coerce.string().min(1),
});
