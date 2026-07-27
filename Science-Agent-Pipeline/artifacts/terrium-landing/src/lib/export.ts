export function trajectoryToCSV(data: Record<string, number>[]): string {
  if (data.length === 0) return '';
  const headers = Object.keys(data[0]!);
  const rows = data.map((row) => headers.map((h) => row[h] ?? '').join(','));
  return [headers.join(','), ...rows].join('\n');
}

export function exportResultJSON(
  result: Record<string, unknown>,
  filename: string,
): void {
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  triggerDownload(url, filename);
  URL.revokeObjectURL(url);
}

export function exportResultCSV(
  trajectory: Record<string, number>[],
  filename: string,
): void {
  const csv = trajectoryToCSV(trajectory);
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  triggerDownload(url, filename);
  URL.revokeObjectURL(url);
}

function triggerDownload(url: string, filename: string): void {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
