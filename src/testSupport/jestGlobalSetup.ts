import { isolateCatervaState, readOldWayUnlessAsked } from './isolatedState';

// See isolatedState.ts for why this has to run in jest's parent process.
export default function globalSetup(): void {
  isolateCatervaState(process.env);
  readOldWayUnlessAsked(process.env);
}
