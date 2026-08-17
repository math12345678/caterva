/**
 * Quote-aware CSV reading, for tests.
 *
 * WHY THIS IS A SHARED FILE
 * -------------------------
 * `line.split(',')` has now produced a wrong assertion three times in this
 * directory, each time in a test whose subject was a column that sits after
 * the JSON-serialised `parameters` cell. That cell contains commas inside
 * quotes, so a naive split shifts every column to its right.
 *
 * The failure mode is the dangerous kind: the assertion does not error, it
 * compares against a fragment of a serialised object — `"vmax":12.8`
 * instead of `unknown` — and the test author reads the diff as a bug in the
 * code under test.
 *
 * Rewriting the splitter per file is what allowed it to happen three times.
 */

/** Split one CSV line into fields, honouring `"` quoting and `""` escapes. */
export function splitCsvLine(line: string): string[] {
  const fields: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      fields.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  fields.push(current);
  return fields;
}

/**
 * The lines a consumer using `comment="#"` would actually parse.
 *
 * Blank lines are dropped too: the exporters emit one before each summary
 * block, and `pandas.read_csv` skips blank lines by default.
 */
export function dataLines(csv: string): string[] {
  return csv.split('\n').filter(l => !l.startsWith('#') && l.trim() !== '');
}

/**
 * One column's value, located by header name.
 *
 * `lineIndex` is an index into `dataLines`, so 0 is the header row and 1 is
 * the first record.
 */
export function columnValue(csv: string, name: string, lineIndex = 1): string {
  const lines = dataLines(csv);
  const headers = splitCsvLine(lines[0]!);
  const i = headers.indexOf(name);
  if (i < 0) {
    throw new Error(`no column named ${name}; header is ${JSON.stringify(headers)}`);
  }
  const row = lines[lineIndex];
  if (row === undefined) {
    throw new Error(`no data row at index ${lineIndex}; there are ${lines.length - 1}`);
  }
  return splitCsvLine(row)[i]!;
}
