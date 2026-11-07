import * as fs from 'fs';

import { STATE_DIR_VAR } from './isolatedState';

export default function globalTeardown(): void {
  const dir = process.env[STATE_DIR_VAR];
  if (dir) fs.rmSync(dir, { recursive: true, force: true });
}
