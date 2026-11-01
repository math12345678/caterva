// Moved from src/integration/scientificPipeline.ts on 2026-09-27 with the SIR domain.

  /**
   * The judgement in an SIR result, separated from the machinery.
   *
   * Static and pure so it can be driven directly: the interesting cases are
   * a truncated window and a resolved epidemic, and neither should need a
   * Python subprocess to assert.
   */
  static summariseSir(
    trajectory: Array<{
      time: number;
      susceptible: number;
      infected: number;
      recovered: number;
    }>,
    gamma: number | null,
    end: number
  ): Record<string, unknown> {
    const peak = trajectory.reduce(
      (best, point) => (point.infected > best.infected ? point : best),
      trajectory[0] ?? { time: 0, infected: 0, susceptible: 0, recovered: 0 }
    );
    const first = trajectory[0];
    const last = trajectory[trajectory.length - 1];

    // A PEAK AT THE EDGE OF THE WINDOW IS NOT A PEAK.
    //
    // `integrationWindowFor` defaults to 10, which is a sensible enzyme
    // assay and far too short for an epidemic: measured with beta 0.3,
    // gamma 0.1, s0 990, i0 10, infections are still climbing steeply at
    // t=10 and do not peak until roughly t=30 at ~290 infected.
    //
    // Reported naively, that window says `peakInfected: 65` — a real number
    // from a real integration, describing the boundary of the run rather
    // than the epidemic. Somebody would plan around it.
    //
    // Three states, not two: a peak that was reached, a peak that was not,
    // and never a boundary silently promoted to a maximum.
    const stillRising =
      trajectory.length > 1 &&
      last !== undefined &&
      peak.time === last.time &&
      last.infected > trajectory[trajectory.length - 2]!.infected;

    return {
        // null, not the boundary value. "I did not see the peak" must never
        // read as "the peak was here", and a number is not improved by
        // being the largest one available.
      peakInfected: stillRising ? null : peak.infected,
      peakTime: stillRising ? null : peak.time,
      peakReachedWithinWindow: !stillRising,
      highestInfectedSeen: peak.infected,
      ...(stillRising
          ? {
              note:
                `Infections were still rising when the run ended at ` +
                `t=${last?.time}. The highest value seen (` +
                `${peak.infected}) is the edge of the window, not the peak ` +
                `of the epidemic. Pass a larger 'end' in parameters — with ` +
                `gamma=${gamma}, the mean infectious ` +
                `period is ${gamma ? 1 / gamma : '?'}, ` +
                `so this window covered under ` +
                `${gamma ? (end * gamma).toFixed(1) : '?'} ` +
                `of them.`,
            }
          : {}),
        finalSusceptible: last?.susceptible ?? 0,
      finalRecovered: last?.recovered ?? 0,
      // Susceptibles who were infected at some point, as a fraction of
      // those who could be. The standard epidemiological reading of this
      // curve, and NOT "conversion percentage".
      attackRate:
        first && first.susceptible > 0
          ? ((first.susceptible - (last?.susceptible ?? 0)) /
              first.susceptible) *
            100
          : 0,
    };
  }
