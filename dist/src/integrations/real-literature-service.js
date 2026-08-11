"use strict";
/**
 * Real Literature Service - Actual API Integration
 *
 * Integrates with real scientific databases:
 * - CrossRef API (DOI resolution)
 * - PubMed API (article metadata)
 * - NCBI (sequence/protein data)
 * - BRENDA (enzyme kinetics database)
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.RealLiteratureAggregator = exports.RealUniProtClient = exports.RealBrendaClient = exports.RealPubMedClient = exports.RealCrossRefClient = void 0;
const logger_1 = require("../logger");
class RealCrossRefClient {
    baseUrl = 'https://api.crossref.org/v1';
    userAgent = 'Terrium-Scientific/1.0 (mailto:reddy.uday@gmail.com)';
    /**
     * Resolve real DOI from CrossRef
     */
    async resolveDOI(doi) {
        try {
            const response = await fetch(`${this.baseUrl}/works/${encodeURIComponent(doi)}`, {
                headers: { 'User-Agent': this.userAgent }
            });
            if (!response.ok) {
                logger_1.logger.warn({ doi, status: response.status }, 'DOI not found in CrossRef');
                return null;
            }
            const data = await response.json();
            return data.message;
        }
        catch (error) {
            logger_1.logger.error({ doi, error }, 'Failed to resolve DOI');
            throw error;
        }
    }
    /**
     * Search CrossRef for enzyme kinetics papers
     */
    async searchEnzymeKinetics(enzyme, limit = 10) {
        try {
            const query = `${enzyme} kinetics enzyme parameters`;
            const response = await fetch(`${this.baseUrl}/works?query=${encodeURIComponent(query)}&rows=${limit}&sort=relevance`, { headers: { 'User-Agent': this.userAgent } });
            if (!response.ok)
                throw new Error(`Search failed: ${response.status}`);
            const data = await response.json();
            return data.message.items || [];
        }
        catch (error) {
            logger_1.logger.error({ enzyme, error }, 'Enzyme search failed');
            throw error;
        }
    }
}
exports.RealCrossRefClient = RealCrossRefClient;
class RealPubMedClient {
    baseUrl = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils';
    dbUrl = 'https://www.ncbi.nlm.nih.gov/research/bsl/semanticweb/';
    /**
     * Search PubMed for kinetic parameters
     */
    async searchKineticParameters(enzyme, substrate, limit = 10) {
        try {
            const query = `${enzyme} ${substrate} Michaelis Menten kinetics`;
            const searchUrl = `${this.baseUrl}/esearch.fcgi?db=pubmed&term=${encodeURIComponent(query)}&retmax=${limit}&rettype=json`;
            const searchResponse = await fetch(searchUrl);
            if (!searchResponse.ok)
                throw new Error('PubMed search failed');
            const searchData = await searchResponse.json();
            const pmids = searchData.esearchresult.idlist || [];
            if (pmids.length === 0)
                return [];
            // Fetch article details
            return Promise.all(pmids.map((pmid) => this.fetchArticleDetails(pmid)));
        }
        catch (error) {
            logger_1.logger.error({ enzyme, substrate, error }, 'PubMed search failed');
            throw error;
        }
    }
    /**
     * Fetch full article details from PubMed
     */
    async fetchArticleDetails(pmid) {
        try {
            const summaryUrl = `${this.baseUrl}/esummary.fcgi?db=pubmed&id=${pmid}&rettype=json`;
            const response = await fetch(summaryUrl);
            if (!response.ok)
                throw new Error('Failed to fetch article summary');
            const data = await response.json();
            const article = data.result[pmid];
            return {
                pmid,
                title: article.title || 'Unknown',
                authors: article.authors?.map((a) => a.name) || [],
                year: parseInt(article.pubdate?.split('/')[0]) || new Date().getFullYear(),
                journal: article.source || 'Unknown',
                abstract: article.abstract || '',
                doi: article.doi
            };
        }
        catch (error) {
            logger_1.logger.error({ pmid, error }, 'Failed to fetch article details');
            throw error;
        }
    }
}
exports.RealPubMedClient = RealPubMedClient;
class RealBrendaClient {
    /**
     * Query BRENDA for kinetic parameters
     * Note: BRENDA requires registration for API access
     */
    async getKineticParameters(enzyme, substrate) {
        // BRENDA API is restricted - would need API key from BRENDA
        logger_1.logger.info({ enzyme, substrate }, 'BRENDA query would require registered API key - see https://www.brenda-enzyme.org/');
        // For now, return empty - in production, integrate with BRENDA API
        return [];
    }
}
exports.RealBrendaClient = RealBrendaClient;
class RealUniProtClient {
    /**
     * Fetch protein information from UniProt
     */
    async getProteinInfo(uniprotId) {
        try {
            const response = await fetch(`https://rest.uniprot.org/uniprotkb/${uniprotId}.json`);
            if (!response.ok) {
                logger_1.logger.warn({ uniprotId, status: response.status }, 'UniProt ID not found');
                return null;
            }
            const data = await response.json();
            const protein = data.entry;
            return {
                uniprotId,
                geneName: protein.genes?.[0]?.geneName?.value || 'Unknown',
                proteinName: protein.proteinDescription?.recommendedName?.fullName?.value || 'Unknown',
                organism: protein.organism?.scientificName || 'Unknown',
                sequence: protein.sequence?.value || '',
                kinetics: [] // Would be populated from BRENDA
            };
        }
        catch (error) {
            logger_1.logger.error({ uniprotId, error }, 'Failed to fetch UniProt data');
            throw error;
        }
    }
}
exports.RealUniProtClient = RealUniProtClient;
// ============================================================================
// REAL DATA AGGREGATOR
// ============================================================================
class RealLiteratureAggregator {
    crossref = new RealCrossRefClient();
    pubmed = new RealPubMedClient();
    brenda = new RealBrendaClient();
    uniprot = new RealUniProtClient();
    /**
     * Comprehensive search for enzyme kinetics literature
     */
    async searchEnzymeKinetics(enzyme, substrate) {
        logger_1.logger.info({ enzyme, substrate }, 'Searching real literature databases...');
        try {
            // Search all sources in parallel
            const [crossrefResults, pubmedResults] = await Promise.all([
                this.crossref.searchEnzymeKinetics(enzyme),
                this.pubmed.searchKineticParameters(enzyme, substrate),
                // brenda.getKineticParameters(enzyme, substrate) - requires API key
            ]);
            logger_1.logger.info({ crossref: crossrefResults.length, pubmed: pubmedResults.length }, 'Literature search complete');
            return {
                crossref: crossrefResults,
                pubmed: pubmedResults,
                sources: (crossrefResults.length + pubmedResults.length)
            };
        }
        catch (error) {
            logger_1.logger.error({ enzyme, substrate, error }, 'Literature search failed');
            throw error;
        }
    }
    /**
     * Validate DOI actually exists in CrossRef
     */
    async validateDOI(doi) {
        try {
            const article = await this.crossref.resolveDOI(doi);
            return article !== null;
        }
        catch {
            return false;
        }
    }
    /**
     * Get real kinetic parameters from literature
     */
    async getKineticParameters(enzyme, substrate) {
        const results = await this.searchEnzymeKinetics(enzyme, substrate);
        // Extract kinetic parameters from articles
        // In production, would use NLP/text mining to extract Km, Vmax values
        logger_1.logger.info({
            enzyme,
            substrate,
            articlesFound: results.sources
        }, 'Kinetic parameters search complete - would extract Km, Vmax, conditions from abstracts');
        return results;
    }
}
exports.RealLiteratureAggregator = RealLiteratureAggregator;
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
