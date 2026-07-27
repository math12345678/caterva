import { Router, type IRouter } from "express";
import healthRouter from "./health";
import simulateRouter from "./simulate";
import pipelineRouter from "./pipeline";
import enzymesRouter from "./enzymes";
import waitlistRouter from "./waitlist";

const router: IRouter = Router();

router.use(healthRouter);
router.use(simulateRouter);
router.use(pipelineRouter);
router.use(enzymesRouter);
router.use(waitlistRouter);

export default router;
