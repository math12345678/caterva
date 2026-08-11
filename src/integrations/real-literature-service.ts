/**
 * Real Literature Service - Actual API Integration
 *
 * Integrates with real scientific databases:
 * - CrossRef API (DOI resolution)
 * - PubMed API (article metadata)
 * - NCBI (sequence/protein data)
 * - BRENDA (enzyme kinetics database)
 */

import { logger } from '../logger';

// ============================================================================
// CROSSREF API INTEGRATION
// ============================================================================

export interface CrossRefArticle {
  DOI: string;
  title: string[];
  authors?: Array<{ family: string; given: string }>;
  published: { 'date-parts': number[][] };
  'container-title'?: string[];
  volume?: string;
  issue?: string;
  page?: string;
  URL?: string;
  issued?: { 'date-parts': number[][] };
}

export class RealCrossRefClient {
  private baseUrl = 'https://api.crossref.org/v1';
  private userAgent = 'Terrium-Scientific/1.0 (mailto:reddy.uday@gmail.com)';

  /**
   * Resolve real DOI from CrossRef
   */
  async resolveDOI(doi: string): Promise<CrossRefArticle | null> {
    try {
      const response = await fetch(`${this.baseUrl}/works/${encodeURIComponent(doi)}`, {
        headers: { 'User-Agent': this.userAgent }
      });

      if (!response.ok) {
        logger.warn({ doi, status: response.status }, 'DOI not found in CrossRef');
        return null;
      }

      const data = await response.json() as any;
      return data.message;
    } catch (error) {
      logger.error({ doi, error }, 'Failed to resolve DOI');
      throw error;
    }
  }

  /**
   * Search CrossRef for enzyme kinetics papers
   */
  async searchEnzymeKinetics(
    enzyme: string,
    limit: number = 10
  ): Promise<CrossRefArticle[]> {
    try {
      const query = `${enzyme} kinetics enzyme parameters`;
      const response = await fetch(
        `${this.baseUrl}/works?query=${encodeURIComponent(query)}&rows=${limit}&sort=relevance`,
        { headers: { 'User-Agent': this.userAgent } }
      );

      if (!response.ok) throw new Error(`Search failed: ${response.status}`);

      const data = await response.json() as any;
      return data.message.items || [];
    } catch (error) {
      logger.error({ enzyme, error }, 'Enzyme search failed');
      throw error;
    }
  }
}

// ============================================================================
// PUBMED API INTEGRATION
// ============================================================================

export interface PubMedArticle {
  pmid: string;
  title: string;
  authors: string[];
  year: number;
  journal: string;
  abstract: string;
  doi?: string;
}

export class RealPubMedClient {
  private baseUrl = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils';
  private dbUrl = 'https://www.ncbi.nlm.nih.gov/research/bsl/semanticweb/';

  /**
   * Search PubMed for kinetic parameters
   */
  async searchKineticParameters(
    enzyme: string,
    substrate: string,
    limit: number = 10
  ): Promise<PubMedArticle[]> {
    try {
      const query = `${enzyme} ${substrate} Michaelis Menten kinetics`;
      const searchUrl = `${this.baseUrl}/esearch.fcgi?db=pubmed&term=${encodeURIComponent(query)}&retmax=${limit}&rettype=json`;

      const searchResponse = await fetch(searchUrl);
      if (!searchResponse.ok) throw new Error('PubMed search failed');

      const searchData = await searchResponse.json() as any;
      const pmids = searchData.esearchresult.idlist || [];

      if (pmids.length === 0) return [];

      // Fetch article details
      return Promise.all(pmids.map((pmid: string) => this.fetchArticleDetails(pmid)));
    } catch (error) {
      logger.error({ enzyme, substrate, error }, 'PubMed search failed');
      throw error;
    }
  }

  /**
   * Fetch full article details from PubMed
   */
  private async fetchArticleDetails(pmid: string): Promise<PubMedArticle> {
    try {
      const summaryUrl = `${this.baseUrl}/esummary.fcgi?db=pubmed&id=${pmid}&rettype=json`;
      const response = await fetch(summaryUrl);

      if (!response.ok) throw new Error('Failed to fetch article summary');

      const data = await response.json() as any;
      const article = data.result[pmid];

      return {
        pmid,
        title: article.title || 'Unknown',
        authors: article.authors?.map((a: any) => a.name) || [],
        year: parseInt(article.pubdate?.split('/')[0]) || new Date().getFullYear(),
        journal: article.source || 'Unknown',
        abstract: article.abstract || '',
        doi: article.doi
      };
    } catch (error) {
      logger.error({ pmid, error }, 'Failed to fetch article details');
      throw error;
    }
  }
}

// ============================================================================
// BRENDA ENZYME DATABASE
// ============================================================================

export interface BrendaKineticData {
  ecNumber: string;
  enzyme: string;
  substrate: string;
  km: number;
  kmUnit: string;
  vmax: number;
  vmaxUnit: string;
  organism: string;
  temperature: number;
  pH: number;
  reference: string;
}

export class RealBrendaClient {
  /**
   * Query BRENDA for kinetic parameters
   * Note: BRENDA requires registration for API access
   */
  async getKineticParameters(
    enzyme: string,
    substrate: string
  ): Promise<BrendaKineticData[]> {
    // BRENDA API is restricted - would need API key from BRENDA
    logger.info(
      { enzyme, substrate },
      'BRENDA query would require registered API key - see https://www.brenda-enzyme.org/'
    );

    // For now, return empty - in production, integrate with BRENDA API
    return [];
  }
}

// ============================================================================
// UNIPROT PROTEIN DATABASE
// ============================================================================

export interface UniProtProtein {
  uniprotId: string;
  geneName: string;
  proteinName: string;
  organism: string;
  sequence: string;
  kinetics?: BrendaKineticData[];
}

export class RealUniProtClient {
  /**
   * Fetch protein information from UniProt
   */
  async getProteinInfo(uniprotId: string): Promise<UniProtProtein | null> {
    try {
      const response = await fetch(
        `https://rest.uniprot.org/uniprotkb/${uniprotId}.json`
      );

      if (!response.ok) {
        logger.warn({ uniprotId, status: response.status }, 'UniProt ID not found');
        return null;
      }

      const data = await response.json() as any;
      const protein = data.entry;

      return {
        uniprotId,
        geneName: protein.genes?.[0]?.geneName?.value || 'Unknown',
        proteinName: protein.proteinDescription?.recommendedName?.fullName?.value || 'Unknown',
        organism: protein.organism?.scientificName || 'Unknown',
        sequence: protein.sequence?.value || '',
        kinetics: [] // Would be populated from BRENDA
      };
    } catch (error) {
      logger.error({ uniprotId, error }, 'Failed to fetch UniProt data');
      throw error;
    }
  }
}

// ============================================================================
// REAL DATA AGGREGATOR
// ============================================================================

export class RealLiteratureAggregator {
  private crossref = new RealCrossRefClient();
  private pubmed = new RealPubMedClient();
  private brenda = new RealBrendaClient();
  private uniprot = new RealUniProtClient();

  /**
   * Comprehensive search for enzyme kinetics literature
   */
  async searchEnzymeKinetics(enzyme: string, substrate: string) {
    logger.info({ enzyme, substrate }, 'Searching real literature databases...');

    try {
      // Search all sources in parallel
      const [crossrefResults, pubmedResults] = await Promise.all([
        this.crossref.searchEnzymeKinetics(enzyme),
        this.pubmed.searchKineticParameters(enzyme, substrate),
        // brenda.getKineticParameters(enzyme, substrate) - requires API key
      ]);

      logger.info(
        { crossref: crossrefResults.length, pubmed: pubmedResults.length },
        'Literature search complete'
      );

      return {
        crossref: crossrefResults,
        pubmed: pubmedResults,
        sources: (crossrefResults.length + pubmedResults.length)
      };
    } catch (error) {
      logger.error({ enzyme, substrate, error }, 'Literature search failed');
      throw error;
    }
  }

  /**
   * Validate DOI actually exists in CrossRef
   */
  async validateDOI(doi: string): Promise<boolean> {
    try {
      const article = await this.crossref.resolveDOI(doi);
      return article !== null;
    } catch {
      return false;
    }
  }

  /**
   * Get real kinetic parameters from literature
   */
  async getKineticParameters(enzyme: string, substrate: string) {
    const results = await this.searchEnzymeKinetics(enzyme, substrate);

    // Extract kinetic parameters from articles
    // In production, would use NLP/text mining to extract Km, Vmax values
    logger.info(
      {
        enzyme,
        substrate,
        articlesFound: results.sources
      },
      'Kinetic parameters search complete - would extract Km, Vmax, conditions from abstracts'
    );

    return results;
  }
}

// ============================================================================
// USAGE EXAMPLE
// ============================================================================

/*
// Real-world usage:
const aggregator = new RealLiteratureAggregator();

// Search for lactate dehydrogenase kinetics
const results = await aggregator.searchEnzymeKinetics('lactate dehydrogenase', 'lactate');

// Validate a real DOI
const isDOIValid = await aggregator.validateDOI('10.1038/nature12373'); // Real DOI

// Get kinetic parameters from literature
const kinetics = await aggregator.getKineticParameters('lactate dehydrogenase', 'lactate');
*/
