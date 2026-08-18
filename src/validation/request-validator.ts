/**
 * Request Validation
 *
 * Comprehensive input validation for all API endpoints
 * Ensures data integrity and prevents malformed requests
 */

import { ScientificPipeline } from '../integration/scientificPipeline';

export interface ValidationError {
  field: string;
  message: string;
  value?: any;
}

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
}

/**
 * Validate simulation request
 */
export function validateSimulationRequest(data: any): ValidationResult {
  const errors: ValidationError[] = [];

  if (!data) {
    errors.push({ field: 'body', message: 'Request body required' });
    return { valid: false, errors };
  }

  // Query validation
  if (!data.query || typeof data.query !== 'string') {
    errors.push({ field: 'query', message: 'query must be a non-empty string', value: data.query });
  }

  // ASKED, NOT REMEMBERED.
  //
  // This was a hardcoded list of four queries, and it had drifted from the
  // pipeline in both directions at once:
  //
  //   - it REJECTED `allosteric`, which the engine implements ("Allosteric
  //     (Hill)" in `kinematicModels`), so a working model was unreachable
  //     over HTTP;
  //   - it ACCEPTED `competitive-inhibition`, `non-competitive-inhibition`
  //     and `product-inhibition`, which the pipeline cannot place on any
  //     domain. Measured: those requests passed validation, were queued,
  //     returned a job id, and the job then reported `status: "complete"`
  //     while carrying `validated: false` and "does not name a domain this
  //     pipeline knows (mm, sir)". The refusal arrived buried inside a
  //     result labelled complete, rather than as a 400 at request time.
  //
  // A validator that keeps its own copy of what the engine supports
  // validates the copy. It now asks the pipeline, which is the thing that
  // actually decides whether the query can run.
  if (data.query && typeof data.query === 'string'
      && !ScientificPipeline.namesAKnownDomain(data.query)) {
    errors.push({
      field: 'query',
      message:
        `query must name a model this pipeline can run: ` +
        `${ScientificPipeline.knownDomainAliases().join(', ')}`,
      value: data.query
    });
  }

  // Parameters validation
  if (!data.parameters || typeof data.parameters !== 'object') {
    errors.push({ field: 'parameters', message: 'parameters must be an object', value: data.parameters });
  } else {
    const requiredParams = ['km', 'vmax', 's0'];
    for (const param of requiredParams) {
      if (!(param in data.parameters)) {
        errors.push({ field: `parameters.${param}`, message: `${param} is required` });
      } else if (typeof data.parameters[param] !== 'number' || data.parameters[param] <= 0) {
        errors.push({
          field: `parameters.${param}`,
          message: `${param} must be a positive number`,
          value: data.parameters[param]
        });
      }
    }
  }

  // Optional fields
  if (data.enzyme && typeof data.enzyme !== 'string') {
    errors.push({ field: 'enzyme', message: 'enzyme must be a string', value: data.enzyme });
  }

  if (data.substrate && typeof data.substrate !== 'string') {
    errors.push({ field: 'substrate', message: 'substrate must be a string', value: data.substrate });
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * Validate sweep request
 */
export function validateSweepRequest(data: any): ValidationResult {
  const errors: ValidationError[] = [];

  if (!data) {
    errors.push({ field: 'body', message: 'Request body required' });
    return { valid: false, errors };
  }

  // Query validation
  if (!data.query || typeof data.query !== 'string') {
    errors.push({ field: 'query', message: 'query must be a non-empty string' });
  } else if (!ScientificPipeline.namesAKnownDomain(data.query)) {
    // `/api/simulate` checks this and `/api/sweep` did not, so the same
    // string was a 400 on one route and an accepted job on the other —
    // then every point of the sweep failed downstream for a reason the
    // caller only saw by reading the finished result.
    errors.push({
      field: 'query',
      message:
        `query must name a model this pipeline can run: ` +
        `${ScientificPipeline.knownDomainAliases().join(', ')}`,
      value: data.query
    });
  }

  // Base parameters validation
  if (!data.baseParameters || typeof data.baseParameters !== 'object') {
    errors.push({ field: 'baseParameters', message: 'baseParameters must be an object' });
  }

  // Sweep parameters validation
  if (!Array.isArray(data.sweepParameters)) {
    errors.push({ field: 'sweepParameters', message: 'sweepParameters must be an array' });
  } else {
    if (data.sweepParameters.length === 0) {
      errors.push({ field: 'sweepParameters', message: 'sweepParameters must contain at least one parameter' });
    }

    for (let i = 0; i < data.sweepParameters.length; i++) {
      const param = data.sweepParameters[i];

      if (!param.name || typeof param.name !== 'string') {
        errors.push({
          field: `sweepParameters[${i}].name`,
          message: 'name must be a non-empty string'
        });
      }

      if (!param.spec || typeof param.spec !== 'string') {
        errors.push({
          field: `sweepParameters[${i}].spec`,
          message: 'spec must be a non-empty string (format: "min:max:step")'
        });
      } else {
        // Validate spec format
        const parts = param.spec.split(':');
        if (parts.length !== 3) {
          errors.push({
            field: `sweepParameters[${i}].spec`,
            message: 'spec must be in format "min:max:step"',
            value: param.spec
          });
        } else {
          const [min, max, step] = parts.map(Number);
          if (isNaN(min) || isNaN(max) || isNaN(step)) {
            errors.push({
              field: `sweepParameters[${i}].spec`,
              message: 'spec values must be valid numbers',
              value: param.spec
            });
          } else if (min >= max) {
            errors.push({
              field: `sweepParameters[${i}].spec`,
              message: 'min must be less than max',
              value: param.spec
            });
          } else if (step <= 0) {
            errors.push({
              field: `sweepParameters[${i}].spec`,
              message: 'step must be positive',
              value: param.spec
            });
          }
        }
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * Validate batch request
 */
export function validateBatchRequest(data: any): ValidationResult {
  const errors: ValidationError[] = [];

  if (!data) {
    errors.push({ field: 'body', message: 'Request body required' });
    return { valid: false, errors };
  }

  // Query validation
  if (!data.query || typeof data.query !== 'string') {
    errors.push({ field: 'query', message: 'query must be a non-empty string' });
  } else if (!ScientificPipeline.namesAKnownDomain(data.query)) {
    // Same check as `/api/simulate` and `/api/sweep`. A batch is the worst
    // route to leave unchecked: one unrunnable query becomes N failed jobs,
    // each recorded, each reporting complete.
    errors.push({
      field: 'query',
      message:
        `query must name a model this pipeline can run: ` +
        `${ScientificPipeline.knownDomainAliases().join(', ')}`,
      value: data.query
    });
  }

  // Parameter sets validation
  if (!Array.isArray(data.parameterSets)) {
    errors.push({ field: 'parameterSets', message: 'parameterSets must be an array' });
  } else {
    if (data.parameterSets.length === 0) {
      errors.push({ field: 'parameterSets', message: 'parameterSets must contain at least one set' });
    }

    for (let i = 0; i < data.parameterSets.length; i++) {
      const params = data.parameterSets[i];

      if (typeof params !== 'object' || params === null) {
        errors.push({
          field: `parameterSets[${i}]`,
          message: 'Each parameter set must be an object'
        });
      } else {
        // Validate the EFFECTIVE set -- baseParameters overlaid by this
        // set -- because that is exactly what the engine runs:
        //
        //   createMultiParamBatchJobs (batch-processor.ts:197)
        //     parameters: { ...baseParameters, ...params }
        //
        // Checking `params` alone made `baseParameters` pointless: every
        // set had to repeat km, vmax and s0 in full, so the field existed
        // but could never carry anything. Worse, the rejection named a
        // parameter the caller HAD supplied -- "s0 is required" for a
        // request whose baseParameters said `s0: 10` -- which sends
        // someone looking in the wrong place. The engine would have run
        // that request without complaint.
        const base =
          data.baseParameters && typeof data.baseParameters === 'object'
            ? data.baseParameters
            : {};
        const effective: Record<string, unknown> = { ...base, ...params };

        const requiredParams = ['km', 'vmax', 's0'];
        for (const param of requiredParams) {
          // Name the place the caller would actually go to fix it.
          const field =
            param in params
              ? `parameterSets[${i}].${param}`
              : param in base
                ? `baseParameters.${param}`
                : `parameterSets[${i}].${param}`;

          if (!(param in effective)) {
            errors.push({
              field,
              message: `${param} is required (supply it in this parameter set or in baseParameters)`
            });
          } else if (
            typeof effective[param] !== 'number' ||
            !Number.isFinite(effective[param] as number) ||
            (effective[param] as number) <= 0
          ) {
            errors.push({
              field,
              message: `${param} must be a positive, finite number`,
              value: effective[param] as number
            });
          }
        }
      }
    }
  }

  // Concurrency validation (optional)
  if (data.concurrency !== undefined) {
    if (typeof data.concurrency !== 'number' || data.concurrency < 1 || data.concurrency > 100) {
      errors.push({
        field: 'concurrency',
        message: 'concurrency must be a number between 1 and 100',
        value: data.concurrency
      });
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * Validate comparison request
 */
export function validateComparisonRequest(data: any): ValidationResult {
  const errors: ValidationError[] = [];

  if (!data) {
    errors.push({ field: 'body', message: 'Request body required' });
    return { valid: false, errors };
  }

  // Parameters validation
  if (!data.parameters || typeof data.parameters !== 'object') {
    errors.push({ field: 'parameters', message: 'parameters must be an object' });
  } else {
    const requiredParams = ['km', 'vmax', 's0'];
    for (const param of requiredParams) {
      if (!(param in data.parameters)) {
        errors.push({ field: `parameters.${param}`, message: `${param} is required` });
      } else if (typeof data.parameters[param] !== 'number' || data.parameters[param] <= 0) {
        errors.push({
          field: `parameters.${param}`,
          message: `${param} must be a positive number`,
          value: data.parameters[param]
        });
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * Validate job comparison request
 */
export function validateJobComparisonRequest(data: any): ValidationResult {
  const errors: ValidationError[] = [];

  if (!data) {
    errors.push({ field: 'body', message: 'Request body required' });
    return { valid: false, errors };
  }

  if (!Array.isArray(data.jobIds)) {
    errors.push({ field: 'jobIds', message: 'jobIds must be an array' });
  } else {
    if (data.jobIds.length < 2) {
      errors.push({ field: 'jobIds', message: 'At least 2 job IDs required' });
    }

    for (let i = 0; i < data.jobIds.length; i++) {
      const jobId = data.jobIds[i];
      if (typeof jobId !== 'string' || jobId.trim().length === 0) {
        errors.push({
          field: `jobIds[${i}]`,
          message: 'Each job ID must be a non-empty string',
          value: jobId
        });
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * Format validation errors as HTTP response
 */
export function formatValidationErrors(errors: ValidationError[]): string {
  return JSON.stringify({
    error: 'Validation failed',
    validationErrors: errors,
    count: errors.length
  });
}
