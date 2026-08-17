#!/usr/bin/env ts-node
/**
 * OpenAPI Client Generator
 *
 * Generates TypeScript/Python/Go/Rust clients from the OpenAPI specification.
 * Can be used programmatically or from the command line.
 *
 * Usage:
 *   ts-node scripts/generate-openapi-clients.ts --language typescript --output ./clients/ts
 *   ts-node scripts/generate-openapi-clients.ts --language python --output ./clients/py
 *
 * Programmatic usage:
 *   import { generateClient } from './generate-openapi-clients';
 *   await generateClient('typescript', './clients/ts');
 */

import * as fs from 'fs';
import * as path from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

interface GeneratorConfig {
  language: string;
  generatorName: string;
  packageName: string;
  outputDir: string;
  packageVersion: string;
}

const GENERATOR_MAP: Record<string, string> = {
  typescript: 'typescript-fetch',
  ts: 'typescript-fetch',
  python: 'python',
  py: 'python',
  go: 'go',
  rust: 'rust',
  java: 'java',
  csharp: 'csharp-dotnet2',
  php: 'php',
  ruby: 'ruby',
};

const SETUP_INSTRUCTIONS: Record<string, string> = {
  typescript: `
📚 TypeScript Setup:
   cd {output}
   npm install
   npm run build

📖 Usage:
   import { DefaultApi } from '{output}';
   const api = new DefaultApi({ basePath: 'http://localhost:3000' });
   const job = await api.simulate({
     query: 'michaelis-menten',
     parameters: { km: 5.2, vmax: 12.8, s0: 10 }
   });
  `,
  python: `
📚 Python Setup:
   cd {output}
   pip install -e .

📖 Usage:
   from openapi_client import ApiClient, DefaultApi
   api = DefaultApi(ApiClient())
   job = api.simulate({
     'query': 'michaelis-menten',
     'parameters': {'km': 5.2, 'vmax': 12.8, 's0': 10}
   })
  `,
  go: `
📚 Go Setup:
   cd {output}
   go mod init github.com/yourusername/terrium-client
   go build ./...

📖 Usage:
   import "github.com/yourusername/terrium-client"
   client := swagger.NewAPIClient(cfg)
   job, _, _ := client.DefaultApi.Simulate(ctx, request)
  `,
  rust: `
📚 Rust Setup:
   cd {output}
   cargo build

📖 Usage:
   use openapi_client::apis::default_api::*;
   let job = simulate(&config, request).await;
  `,
};

async function ensureOpenAPIGeneratorInstalled(): Promise<void> {
  try {
    await execAsync('openapi-generator-cli version');
  } catch {
    console.log('📦 Installing @openapitools/openapi-generator-cli...');
    await execAsync('npm install -g @openapitools/openapi-generator-cli');
  }
}

async function getOpenAPISpec(specPath: string): Promise<string> {
  const projectRoot = path.resolve(__dirname, '..');
  const localPath = path.join(projectRoot, 'openapi.yaml');

  if (fs.existsSync(localPath)) {
    return localPath;
  }

  // Try remote
  const remoteUrl = `${process.env.TERRIUM_URL || 'http://localhost:3000'}/api/openapi.json`;
  console.log(`ℹ️  Using remote spec: ${remoteUrl}`);
  return remoteUrl;
}

async function generateClient(
  language: string,
  outputDir: string = '',
  packageName: string = 'terrium-client',
  packageVersion: string = '1.0.0'
): Promise<void> {
  // Validate language
  if (!GENERATOR_MAP[language]) {
    throw new Error(
      `❌ Unsupported language: ${language}\n` +
      `Supported: ${Object.keys(GENERATOR_MAP).join(', ')}`
    );
  }

  const generatorName = GENERATOR_MAP[language];
  const finalOutputDir = outputDir || `./generated-client-${language}`;

  const config: GeneratorConfig = {
    language,
    generatorName,
    packageName,
    outputDir: finalOutputDir,
    packageVersion,
  };

  console.log('🔧 Generating client...');
  console.log(`   Language: ${config.language}`);
  console.log(`   Generator: ${config.generatorName}`);
  console.log(`   Output: ${config.outputDir}`);
  console.log(`   Package: ${config.packageName}@${config.packageVersion}`);
  console.log('');

  // Ensure generator is installed
  await ensureOpenAPIGeneratorInstalled();

  // Get spec
  const spec = await getOpenAPISpec('openapi.yaml');

  console.log(`📋 Using spec: ${spec}`);
  console.log('');

  // Generate
  const cmd = [
    'openapi-generator-cli generate',
    `-i "${spec}"`,
    `-g ${config.generatorName}`,
    `-o "${config.outputDir}"`,
    `-p packageName="${config.packageName}"`,
    `-p packageVersion="${config.packageVersion}"`,
    '--skip-validate-spec',
  ].join(' ');

  console.log('⏳ Generating...');
  await execAsync(cmd);

  console.log('');
  console.log('✅ Client generated successfully!');
  console.log('');
  console.log('📁 Generated files:');

  if (fs.existsSync(config.outputDir)) {
    const files = fs.readdirSync(config.outputDir);
    files.forEach(file => {
      const fullPath = path.join(config.outputDir, file);
      const stat = fs.statSync(fullPath);
      const icon = stat.isDirectory() ? '📂' : '📄';
      console.log(`   ${icon} ${file}`);
    });
  }

  console.log('');

  // Show instructions
  if (SETUP_INSTRUCTIONS[language]) {
    console.log(SETUP_INSTRUCTIONS[language].replace(/{output}/g, config.outputDir));
  }

  console.log('🎉 Done! Your generated client is ready to use.');
}

// CLI entry point
async function main() {
  const args = process.argv.slice(2);

  let language = 'typescript';
  let outputDir = '';
  let packageName = 'terrium-client';
  let packageVersion = '1.0.0';

  // Parse arguments
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--language' || args[i] === '-l') {
      language = args[++i];
    } else if (args[i] === '--output' || args[i] === '-o') {
      outputDir = args[++i];
    } else if (args[i] === '--package' || args[i] === '-p') {
      packageName = args[++i];
    } else if (args[i] === '--version' || args[i] === '-v') {
      packageVersion = args[++i];
    } else if (args[i] === '--help' || args[i] === '-h') {
      console.log(`
OpenAPI Client Generator

Usage:
  ts-node scripts/generate-openapi-clients.ts [options]

Options:
  -l, --language <lang>    Target language (default: typescript)
  -o, --output <dir>       Output directory (default: ./generated-client-<lang>)
  -p, --package <name>     Package name (default: terrium-client)
  -v, --version <version>  Package version (default: 1.0.0)
  -h, --help               Show this help

Supported languages:
  ${Object.keys(GENERATOR_MAP).join(', ')}

Examples:
  ts-node scripts/generate-openapi-clients.ts -l typescript -o ./clients/ts
  ts-node scripts/generate-openapi-clients.ts -l python -o ./clients/py
  ts-node scripts/generate-openapi-clients.ts -l go -o ./clients/go
      `);
      process.exit(0);
    }
  }

  try {
    await generateClient(language, outputDir, packageName, packageVersion);
  } catch (error) {
    console.error('❌ Error:', error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
}

// Export for programmatic use
export { generateClient };

// Run if called directly
if (require.main === module) {
  main();
}
