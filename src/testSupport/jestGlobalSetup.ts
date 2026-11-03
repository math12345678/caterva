import { isolateCatervaState } from './isolatedState';

// See isolatedState.ts for why this has to run in jest's parent process.
export default function globalSetup(): void {
  isolateCatervaState(process.env);
}
