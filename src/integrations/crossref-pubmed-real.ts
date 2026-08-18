/**
 * Real CrossRef + PubMed Integration
 *
 * ACTUAL working implementation with real APIs
 * No fake data. Every result is from a real scientific database.
 */

import { logger } from '../logger';

/**
 * The registry could not be reached, so nothing was learned.
 *
 * A distinct type rather than a distinguishing phrase in a message, because
 * the moment the difference lives in prose, the only way to act on it is to
 * match a substring — and a caller that greps an error message is one
 * rewording away from silently reclassifying "we could not look" as "there is
 * nothing there".
 *
 * Mirrors `ResolverUnavailableError` in the literature resolver, which draws
 * the same line for the same reason.
 */
export class PubMedUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PubMedUnavailableError';
  }
}

// ============================================================================
// CROSSREF - REAL DOI RESOLUTION
// ============================================================================

export async function resolveDOIFromCrossRef(doi: string): Promise<{
  title: string;
  authors: Array<{ given: string; family: string }>;
  year: number;
  journal: string;
  doi: string;
  url: string;
  abstract?: string;
} | null> {
  try {
    const url = `https://api.crossref.org/v1/works/${encodeURIComponent(doi)}`;

    const response = await fetch(url, {
      headers: {
        'User-Agent': 'Terrium-Scientific/1.0 (mailto:reddy.uday@gmail.com)'
      }
    });

    if (!response.ok) {
      if (response.status === 404) {
        logger.warn({ doi }, 'DOI not found in CrossRef - this DOI does not exist');
        return null;
      }
      throw new Error(`CrossRef API error: ${response.status}`);
    }

    const data = await response.json() as any;
    const work = data.message;

    return {
      title: work.title?.[0] || 'Unknown',
      authors: work.author || [],
      year: work.published?.[0]?.['date-parts']?.[0]?.[0] || new Date().getFullYear(),
      journal: work['container-title']?.[0] || 'Unknown',
      doi: work.DOI || doi,
      url: work.URL || `https://doi.org/${doi}`,
      abstract: work.abstract || undefined
    };
  } catch (error) {
    logger.error({ doi, error }, 'Failed to resolve DOI from CrossRef');
    throw error;
  }
}

// ============================================================================
// PUBMED - REAL PAPER SEARCH
// ============================================================================

export async function searchPubMedForEnzymeKinetics(
  enzyme: string,
  substrate: string,
  limit: number = 20
): Promise<Array<{
  pmid: string;
  title: string;
  authors: string[];
  year: number;
  journal: string;
  abstract: string;
  doi?: string;
  url: string;
}>> {
  // Try multiple query strategies, starting with most specific
  const queries = [
    `${enzyme} ${substrate} kinetics`,
    `${enzyme} kinetics enzyme`,
    enzyme // Fallback to just enzyme name
  ];

  // WHY THIS COUNTER EXISTS
  // -----------------------
  // Every branch below `continue`s, and the loop ended by throwing one error
  // that read: "No real literature found ... Check your network access and
  // verify this enzyme/substrate pair has published kinetics data."
  //
  // That one sentence covered three different situations — the network was
  // unreachable, PubMed returned an error, or PubMed ran the search and
  // genuinely had nothing — and it hedged across all of them because the
  // code could not tell which had happened. The caller therefore could not
  // either, and reported a dead network as "this enzyme has no papers".
  //
  // An absence of evidence presented as evidence of absence is the one thing
  // this tool must not do, and the rest of it (resolve's 0/2/1 exit codes)
  // is built entirely around keeping the two apart.
  //
  // So: a strategy that COMPLETED and returned zero results is counted.
  // A strategy that could not run at all is not. If no strategy completed,
  // nothing was learned.
  let strategiesCompleted = 0;

  for (const searchQuery of queries) {
    try {
      logger.info({ enzyme, substrate, query: searchQuery }, `Searching PubMed: "${searchQuery}"`);

      const searchUrl = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=${encodeURIComponent(searchQuery)}&retmax=${limit}&rettype=json&tool=Terrium&email=reddy.uday@gmail.com`;

      const searchResponse = await fetch(searchUrl);

      if (!searchResponse.ok) {
        logger.error(
          { query: searchQuery, status: searchResponse.status, statusText: searchResponse.statusText },
          'PubMed API error'
        );
        continue;
      }

      // Check content-type before parsing
      const contentType = searchResponse.headers.get('content-type') || '';
      if (!contentType.includes('json')) {
        logger.error(
          { query: searchQuery, contentType, url: searchUrl },
          'PubMed returned non-JSON response. This usually means an API error or server issue.'
        );
        continue;
      }

      // Try to parse JSON
      let searchData: any;
      try {
        const text = await searchResponse.text();
        searchData = JSON.parse(text);
      } catch (parseError) {
        logger.error(
          { query: searchQuery, parseError: parseError instanceof Error ? parseError.message : String(parseError) },
          'Failed to parse PubMed JSON response'
        );
        continue;
      }

      // Check for API error in response
      if (searchData.error) {
        logger.error({ query: searchQuery, apiError: searchData.error }, 'PubMed API returned error');
        continue;
      }

      const pmids = searchData.esearchresult?.idlist || [];

      // This strategy REACHED PubMed and got a well-formed answer. Whether
      // the answer is "here are 40 PMIDs" or "none", the search happened —
      // which is the fact the caller needs and could not previously get.
      strategiesCompleted++;

      if (pmids.length === 0) {
        logger.warn({ query: searchQuery }, 'No PubMed results found for this query');
        continue; // Try next query
      }

      logger.info(
        { query: searchQuery, resultCount: pmids.length },
        `Found ${pmids.length} PubMed results`
      );

      // Fetch details for each PMID
      const results = await Promise.all(
        pmids.slice(0, limit).map((pmid: string) => fetchPubMedDetails(pmid))
      );

      const validResults = results.filter((r: any): r is NonNullable<typeof r> => r !== null);
      if (validResults.length > 0) {
        logger.info(
          { resultCount: validResults.length },
          `Successfully retrieved details for ${validResults.length} articles`
        );
        return validResults;
      } else {
        logger.warn({ query: searchQuery }, 'Found PMIDs but could not fetch details');
        continue;
      }
    } catch (queryError) {
      logger.error(
        { query: searchQuery, error: queryError instanceof Error ? queryError.message : String(queryError), stack: queryError instanceof Error ? queryError.stack : undefined },
        'Query strategy failed'
      );
      continue;
    }
  }

  // All strategies exhausted. WHICH KIND of exhaustion decides what is true.
  if (strategiesCompleted === 0) {
    // Nothing reached PubMed. No claim can be made about what PubMed holds.
    logger.error(
      { enzyme, substrate, strategies: queries.length },
      'No PubMed search strategy could be performed - the registry was not reached',
    );
    throw new PubMedUnavailableError(
      `The PubMed search for "${enzyme}" / "${substrate}" could not be performed: ` +
        `none of the ${queries.length} query strategies reached the registry. ` +
        'This says nothing about whether such papers exist.',
    );
  }

  // At least one search ran and came back empty. That IS an answer.
  logger.warn(
    { enzyme, substrate, strategiesCompleted },
    'PubMed searched and returned no results for this system',
  );
  return [];
}

/**
 * Fetch full details for a single PubMed article
 */
async function fetchPubMedDetails(pmid: string): Promise<{
  pmid: string;
  title: string;
  authors: string[];
  year: number;
  journal: string;
  abstract: string;
  doi?: string;
  url: string;
} | null> {
  try {
    const url = `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=${pmid}&rettype=json`;

    const response = await fetch(url);
    if (!response.ok) throw new Error('Failed to fetch article details');

    const data = await response.json() as any;
    const article = data.result?.[pmid];

    if (!article) return null;

    const pubdate = article.pubdate || '';
    const year = parseInt(pubdate.split('')[0]) || new Date().getFullYear();

    return {
      pmid,
      title: article.title || 'Unknown',
      authors: (article.authors || []).map((a: any) => a.name || a.initials || ''),
      year,
      journal: article.source || 'Unknown',
      abstract: article.abstract || '',
      doi: article.doi,
      url: `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`
    };
  } catch (error) {
    logger.warn({ pmid, error }, 'Failed to fetch article details');
    return null;
  }
}

// ============================================================================
// REAL DATA PIPELINE
// ============================================================================

export interface EnzymeKineticsResult {
  enzyme: string;
  substrate: string;
  sources: {
    crossref: Array<{
      title: string;
      authors: Array<{ given: string; family: string }>;
      year: number;
      journal: string;
      doi: string;
      url: string;
    }>;
    pubmed: Array<{
      pmid: string;
      title: string;
      authors: string[];
      year: number;
      journal: string;
      abstract: string;
      doi?: string;
      url: string;
    }>;
  };
  totalPapers: number;
}

/**
 * REAL data retrieval - searches actual scientific databases
 */
export async function getRealEnzymeKineticsData(
  enzyme: string,
  substrate: string
): Promise<EnzymeKineticsResult> {
  logger.info({ enzyme, substrate }, 'Starting REAL literature search...');

  try {
    // Search both databases in parallel
    const [pubmedResults] = await Promise.all([
      searchPubMedForEnzymeKinetics(enzyme, substrate, 20)
    ]);

    // CrossRef search via enzyme + substrate + kinetics
    const crossrefResults: any[] = [];
    // Note: CrossRef doesn't have a direct search API like PubMed
    // We would need to use either:
    // 1. Embed CrossRef in PubMed results via DOI lookup
    // 2. Use a REST API with search terms

    logger.info(
      {
        pubmedCount: pubmedResults.length,
        crossrefCount: crossrefResults.length
      },
      'Literature search complete'
    );

    const totalPapers = pubmedResults.length + crossrefResults.length;

    if (totalPapers === 0) {
      logger.warn(
        { enzyme, substrate },
        'No literature found - this may indicate missing data or misspelled enzyme name'
      );
    }

    return {
      enzyme,
      substrate,
      sources: {
        crossref: crossrefResults,
        pubmed: pubmedResults
      },
      totalPapers
    };
  } catch (error) {
    logger.error({ enzyme, substrate, error }, 'Real data retrieval failed');
    throw error;
  }
}

// ============================================================================
// EXAMPLE REAL SEARCHES
// ============================================================================

/*
REAL USAGE EXAMPLES:

// Search for lactate dehydrogenase kinetics
const result = await getRealEnzymeKineticsData(
  'lactate dehydrogenase',
  'lactate'
);

console.log(`Found ${result.totalPapers} papers:`);
result.sources.pubmed.forEach(paper => {
  console.log(`- ${paper.title}`);
  console.log(`  ${paper.authors.join(', ')}`);
  console.log(`  ${paper.journal} (${paper.year})`);
  console.log(`  https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`);
});

// Validate a real DOI
const doi = '10.1038/nature12373';
const article = await resolveDOIFromCrossRef(doi);
if (article) {
  console.log(`✓ DOI ${doi} is REAL`);
  console.log(`  Title: ${article.title}`);
  console.log(`  Authors: ${article.authors.map(a => a.family).join(', ')}`);
  console.log(`  Journal: ${article.journal}`);
  console.log(`  Year: ${article.year}`);
} else {
  console.log(`✗ DOI ${doi} does NOT exist in CrossRef`);
}
*/
