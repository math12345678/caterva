/**
 * Job Query Builder
 *
 * Advanced filtering and querying for job history
 * Allows complex queries on job records
 */

export interface JobFilter {
  status?: 'complete' | 'error' | 'running';
  query?: string;
  validated?: boolean;
  dateFrom?: Date;
  dateTo?: Date;
  minConfidence?: number;
  maxConfidence?: number;
  minDuration?: number;
  maxDuration?: number;
  limit?: number;
  offset?: number;
  sortBy?: 'date' | 'confidence' | 'duration' | 'finalValue';
  sortOrder?: 'asc' | 'desc';
}

export interface QueryResult {
  jobs: any[];
  total: number;
  filtered: number;
  limit: number;
  offset: number;
}

/**
 * Parse query string into filter object
 */
export function parseQueryString(queryStr: string): JobFilter {
  const params = new URLSearchParams(queryStr);
  const filter: JobFilter = {};

  if (params.has('status')) {
    const status = params.get('status');
    if (['complete', 'error', 'running'].includes(status!)) {
      filter.status = status as any;
    }
  }

  if (params.has('query')) {
    filter.query = params.get('query') || undefined;
  }

  if (params.has('validated')) {
    filter.validated = params.get('validated') === 'true';
  }

  if (params.has('dateFrom')) {
    const date = new Date(params.get('dateFrom')!);
    if (!isNaN(date.getTime())) {
      filter.dateFrom = date;
    }
  }

  if (params.has('dateTo')) {
    const date = new Date(params.get('dateTo')!);
    if (!isNaN(date.getTime())) {
      filter.dateTo = date;
    }
  }

  if (params.has('minConfidence')) {
    const val = parseFloat(params.get('minConfidence')!);
    if (!isNaN(val)) filter.minConfidence = val;
  }

  if (params.has('maxConfidence')) {
    const val = parseFloat(params.get('maxConfidence')!);
    if (!isNaN(val)) filter.maxConfidence = val;
  }

  if (params.has('minDuration')) {
    const val = parseInt(params.get('minDuration')!);
    if (!isNaN(val)) filter.minDuration = val;
  }

  if (params.has('maxDuration')) {
    const val = parseInt(params.get('maxDuration')!);
    if (!isNaN(val)) filter.maxDuration = val;
  }

  if (params.has('limit')) {
    const val = parseInt(params.get('limit')!);
    if (!isNaN(val)) filter.limit = Math.min(val, 10000); // Max 10k
  } else {
    filter.limit = 50; // Default
  }

  if (params.has('offset')) {
    const val = parseInt(params.get('offset')!);
    if (!isNaN(val)) filter.offset = val;
  } else {
    filter.offset = 0;
  }

  if (params.has('sortBy')) {
    const sortBy = params.get('sortBy');
    if (['date', 'confidence', 'duration', 'finalValue'].includes(sortBy!)) {
      filter.sortBy = sortBy as any;
    }
  }

  if (params.has('sortOrder')) {
    const order = params.get('sortOrder');
    if (['asc', 'desc'].includes(order!)) {
      filter.sortOrder = order as any;
    }
  }

  return filter;
}

/**
 * Apply filter to job array
 */
export function filterJobs(jobs: any[], filter: JobFilter): QueryResult {
  let filtered = [...jobs];

  // Status filter
  if (filter.status) {
    filtered = filtered.filter(job => job.status === filter.status);
  }

  // Query (model) filter
  if (filter.query) {
    filtered = filtered.filter(job =>
      job.query && job.query.toLowerCase().includes(filter.query!.toLowerCase())
    );
  }

  // Validation filter
  if (filter.validated !== undefined) {
    filtered = filtered.filter(job => (job.result?.validated || false) === filter.validated);
  }

  // Date range filter.
  //
  // BOTH bounds test `startTime`. `dateTo` used to test `endTime`, which
  // made the range asymmetric and dropped precisely the jobs a date query
  // is most often asked for: a job that errored or is still running has no
  // `endTime`, so `new Date(undefined) <= dateTo` is false and it vanished.
  //
  // In the fixture that caught this, `job_3` (status 'error', started 12:00
  // inside the window, never finished) was silently absent from "everything
  // on 2026-08-11". Someone debugging a bad day would have been shown only
  // the runs that went well.
  //
  // "Jobs started in this window" is also what a reader means by a date
  // range, and it keeps a long-running job from disappearing merely because
  // it crossed midnight.
  if (filter.dateFrom) {
    filtered = filtered.filter(job =>
      job.startTime && new Date(job.startTime) >= filter.dateFrom!
    );
  }

  if (filter.dateTo) {
    filtered = filtered.filter(job =>
      job.startTime && new Date(job.startTime) <= filter.dateTo!
    );
  }

  // Confidence filter
  if (filter.minConfidence !== undefined) {
    filtered = filtered.filter(job =>
      (job.result?.confidence || 0) >= filter.minConfidence!
    );
  }

  if (filter.maxConfidence !== undefined) {
    filtered = filtered.filter(job =>
      (job.result?.confidence || 0) <= filter.maxConfidence!
    );
  }

  // Duration filter
  if (filter.minDuration !== undefined) {
    filtered = filtered.filter(job => (job.duration || 0) >= filter.minDuration!);
  }

  if (filter.maxDuration !== undefined) {
    filtered = filtered.filter(job => (job.duration || 0) <= filter.maxDuration!);
  }

  const totalFiltered = filtered.length;

  // Sorting
  const sortBy = filter.sortBy || 'date';
  const sortOrder = filter.sortOrder || 'desc';

  filtered.sort((a, b) => {
    let aVal: any, bVal: any;

    switch (sortBy) {
      case 'confidence':
        aVal = a.result?.confidence || 0;
        bVal = b.result?.confidence || 0;
        break;
      case 'duration':
        aVal = a.duration || 0;
        bVal = b.duration || 0;
        break;
      case 'finalValue':
        aVal = a.result?.finalValue || 0;
        bVal = b.result?.finalValue || 0;
        break;
      case 'date':
      default:
        aVal = a.startTime || 0;
        bVal = b.startTime || 0;
    }

    const comparison = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
    return sortOrder === 'desc' ? -comparison : comparison;
  });

  // Pagination
  const offset = filter.offset || 0;
  const limit = filter.limit || 50;
  const paginatedJobs = filtered.slice(offset, offset + limit);

  return {
    jobs: paginatedJobs,
    total: jobs.length,
    filtered: totalFiltered,
    limit,
    offset
  };
}

/**
 * Build query URL from filter
 */
export function buildQueryUrl(filter: JobFilter): string {
  const params = new URLSearchParams();

  if (filter.status) params.set('status', filter.status);
  if (filter.query) params.set('query', filter.query);
  if (filter.validated !== undefined) params.set('validated', String(filter.validated));
  if (filter.dateFrom) params.set('dateFrom', filter.dateFrom.toISOString());
  if (filter.dateTo) params.set('dateTo', filter.dateTo.toISOString());
  if (filter.minConfidence !== undefined) params.set('minConfidence', String(filter.minConfidence));
  if (filter.maxConfidence !== undefined) params.set('maxConfidence', String(filter.maxConfidence));
  if (filter.minDuration !== undefined) params.set('minDuration', String(filter.minDuration));
  if (filter.maxDuration !== undefined) params.set('maxDuration', String(filter.maxDuration));
  if (filter.limit) params.set('limit', String(filter.limit));
  if (filter.offset) params.set('offset', String(filter.offset));
  if (filter.sortBy) params.set('sortBy', filter.sortBy);
  if (filter.sortOrder) params.set('sortOrder', filter.sortOrder);

  return params.toString();
}

/**
 * Generate common filter presets
 */
export const FilterPresets = {
  recentSuccessful: (): JobFilter => ({
    status: 'complete',
    limit: 50,
    sortBy: 'date',
    sortOrder: 'desc'
  }),

  highConfidence: (): JobFilter => ({
    minConfidence: 0.9,
    limit: 50,
    sortBy: 'confidence',
    sortOrder: 'desc'
  }),

  failures: (): JobFilter => ({
    status: 'error',
    limit: 50,
    sortBy: 'date',
    sortOrder: 'desc'
  }),

  today: (): JobFilter => {
    const now = new Date();
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return {
      dateFrom: midnight,
      dateTo: now,
      limit: 1000,
      sortBy: 'date',
      sortOrder: 'desc'
    };
  },

  lastWeek: (): JobFilter => {
    const now = new Date();
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    return {
      dateFrom: weekAgo,
      dateTo: now,
      limit: 1000,
      sortBy: 'date',
      sortOrder: 'desc'
    };
  },

  michaelisMenten: (): JobFilter => ({
    query: 'michaelis-menten',
    limit: 50,
    sortBy: 'date',
    sortOrder: 'desc'
  }),

  competitiveInhibition: (): JobFilter => ({
    query: 'competitive-inhibition',
    limit: 50,
    sortBy: 'date',
    sortOrder: 'desc'
  }),

  validated: (): JobFilter => ({
    validated: true,
    limit: 50,
    sortBy: 'confidence',
    sortOrder: 'desc'
  }),

  unvalidated: (): JobFilter => ({
    validated: false,
    limit: 50,
    sortBy: 'date',
    sortOrder: 'desc'
  })
};
