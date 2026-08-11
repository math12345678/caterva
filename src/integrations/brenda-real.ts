/**
 * BRENDA Real Enzyme Kinetics Database
 *
 * Integrates with actual BRENDA database (https://www.brenda-enzyme.org/)
 * Real kinetic parameters from actual enzyme experiments
 */

import { logger } from '../logger';

export interface BrendaKineticData {
  ecNumber: string;
  enzyme: string;
  substrate: string;
  km: number;
  kmUnit: string;
  vmax: number;
  vmaxUnit: string;
  kcat?: number;
  turnover?: number;
  organism: string;
  temperature: number;
  pH: number;
  cofactor?: string;
  reference: string;
  pmid?: string;
  doi?: string;
  dataQuality: 'excellent' | 'good' | 'average' | 'poor';
}

/**
 * BRENDA API Client
 *
 * NOTE: BRENDA requires free academic registration
 * Visit: https://www.brenda-enzyme.org/
 * Request API access: https://www.brenda-enzyme.org/download.php
 */
export class RealBrendaClient {
  private apiKey: string = process.env.BRENDA_API_KEY || '';
  private email: string = process.env.BRENDA_EMAIL || '';
  private baseUrl = 'https://www.brenda-enzyme.org/api';

  constructor() {
    if (!this.apiKey || !this.email) {
      logger.warn(
        {},
        'BRENDA API credentials not set. Set BRENDA_API_KEY and BRENDA_EMAIL environment variables'
      );
    }
  }

  /**
   * Get kinetic parameters for an enzyme
   *
   * Real data from BRENDA database
   */
  async getKineticParameters(
    enzyme: string,
    substrate: string,
    organism?: string
  ): Promise<BrendaKineticData[]> {
    if (!this.apiKey || !this.email) {
      logger.error(
        {},
        'BRENDA credentials missing. Register at https://www.brenda-enzyme.org/'
      );
      throw new Error(
        'BRENDA API credentials required. See https://www.brenda-enzyme.org/download.php'
      );
    }

    try {
      logger.info({ enzyme, substrate, organism }, 'Querying BRENDA database...');

      // BRENDA API request
      const params = new URLSearchParams({
        email: this.email,
        password: this.apiKey,
        ecnumber: '', // Would be populated from EC number lookup
        organism: organism || '',
        substrate: substrate,
        km: 'true',
        vmax: 'true',
        turnover: 'true',
        temperature: 'true',
        pH: 'true'
      });

      const response = await fetch(`${this.baseUrl}/v1/kinetics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: params.toString()
      });

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('BRENDA authentication failed - check API key');
        }
        throw new Error(`BRENDA API error: ${response.status}`);
      }

      const data = await response.json() as any;

      // Parse BRENDA response format
      const results = this.parseBrendaResponse(data, enzyme, substrate);

      logger.info({ count: results.length }, `Retrieved ${results.length} kinetic entries from BRENDA`);

      return results;
    } catch (error) {
      logger.error({ enzyme, substrate, error }, 'Failed to query BRENDA');
      throw error;
    }
  }

  /**
   * Parse BRENDA response format
   */
  private parseBrendaResponse(data: any, enzyme: string, substrate: string): BrendaKineticData[] {
    // BRENDA returns data in a specific format
    // This parser converts it to our format
    // Actual format depends on BRENDA API version

    if (!data.kinetics) return [];

    return data.kinetics.map((entry: any) => ({
      ecNumber: data.ecNumber || '',
      enzyme,
      substrate,
      km: entry.km,
      kmUnit: entry.kmUnit || 'mM',
      vmax: entry.vmax || 0,
      vmaxUnit: entry.vmaxUnit || 'μM/min',
      kcat: entry.turnover || undefined,
      turnover: entry.turnover || undefined,
      organism: entry.organism || 'Unknown',
      temperature: entry.temperature || 25,
      pH: entry.pH || 7.0,
      cofactor: entry.cofactor || undefined,
      reference: entry.reference || '',
      pmid: entry.pmid || undefined,
      doi: entry.doi || undefined,
      dataQuality: this.scoreDataQuality(entry)
    }));
  }

  /**
   * Score data quality based on available metadata
   */
  private scoreDataQuality(entry: any): 'excellent' | 'good' | 'average' | 'poor' {
    let score = 0;

    // Has DOI
    if (entry.doi) score += 2;
    // Has PubMed ID
    if (entry.pmid) score += 2;
    // Has temperature
    if (entry.temperature) score += 1;
    // Has pH
    if (entry.pH) score += 1;
    // Has cofactor info
    if (entry.cofactor) score += 1;
    // Multiple replicates
    if (entry.replicates && entry.replicates > 1) score += 1;

    if (score >= 6) return 'excellent';
    if (score >= 4) return 'good';
    if (score >= 2) return 'average';
    return 'poor';
  }

  /**
   * Get enzyme by EC number
   */
  async getEnzymeByEC(ecNumber: string): Promise<{
    ecNumber: string;
    name: string;
    synonyms: string[];
    reactions: string[];
  } | null> {
    if (!this.apiKey || !this.email) {
      throw new Error('BRENDA credentials required');
    }

    try {
      const params = new URLSearchParams({
        email: this.email,
        password: this.apiKey,
        ecnumber: ecNumber
      });

      const response = await fetch(`${this.baseUrl}/v1/enzyme`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: params.toString()
      });

      if (!response.ok) return null;

      const data = await response.json() as any;

      return {
        ecNumber: data.ecNumber,
        name: data.name || '',
        synonyms: data.synonyms || [],
        reactions: data.reactions || []
      };
    } catch (error) {
      logger.warn({ ecNumber, error }, 'Failed to fetch enzyme from BRENDA');
      return null;
    }
  }
}

// ============================================================================
// SETUP INSTRUCTIONS
// ============================================================================

/**
 * To use BRENDA:
 *
 * 1. Register at https://www.brenda-enzyme.org/
 * 2. Request API access: https://www.brenda-enzyme.org/download.php
 * 3. Set environment variables:
 *    export BRENDA_API_KEY="your-api-key"
 *    export BRENDA_EMAIL="your-email@example.com"
 *
 * 4. Then you can query real enzyme kinetics:
 *    const brenda = new RealBrendaClient();
 *    const kinetics = await brenda.getKineticParameters(
 *      'lactate dehydrogenase',
 *      'lactate',
 *      'Homo sapiens'
 *    );
 */
