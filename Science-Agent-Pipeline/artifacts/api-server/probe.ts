import { interpret } from "./src/lib/labelQueryLog";
for (const i of ["mm_", "mm_comp", "gillespie_ssa_b", "gillespie_ssa_r", "mm", "gillespie_ssa", "mm_competitive_inhibition"])
  console.log(`  ${JSON.stringify(i).padEnd(30)} -> ${JSON.stringify(interpret(i))}`);
