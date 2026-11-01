#!/bin/bash
# Generate API clients from OpenAPI specification
# Usage: ./scripts/generate-client.sh [language] [output_dir]
#
# Supported languages: typescript, python, go, rust, java
#
# Examples:
#   ./scripts/generate-client.sh typescript ./generated-ts
#   ./scripts/generate-client.sh python ./generated-py
#   ./scripts/generate-client.sh go ./generated-go

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OPENAPI_FILE="$PROJECT_ROOT/openapi.yaml"
OPENAPI_URL="${CATERVA_URL:-http://localhost:3000}/api/openapi.json"

# Parse arguments
LANGUAGE="${1:-typescript}"
OUTPUT_DIR="${2:-./generated-client-$LANGUAGE}"
PACKAGE_NAME="${3:-caterva-client}"
PACKAGE_VERSION="${4:-1.0.0}"

# Map language to generator
case $LANGUAGE in
  typescript)
    GENERATOR="typescript-fetch"
    ;;
  ts)
    GENERATOR="typescript-fetch"
    ;;
  python)
    GENERATOR="python"
    ;;
  py)
    GENERATOR="python"
    ;;
  go)
    GENERATOR="go"
    ;;
  rust)
    GENERATOR="rust"
    ;;
  java)
    GENERATOR="java"
    ;;
  *)
    echo "❌ Unsupported language: $LANGUAGE"
    echo "Supported: typescript, python, go, rust, java"
    exit 1
    ;;
esac

echo "🔧 Generating $LANGUAGE client..."
echo "   Generator: $GENERATOR"
echo "   Output: $OUTPUT_DIR"
echo "   Package: $PACKAGE_NAME@$PACKAGE_VERSION"
echo ""

# Check if openapi-generator-cli is installed
if ! command -v openapi-generator-cli &> /dev/null; then
  echo "📦 Installing @openapitools/openapi-generator-cli..."
  npm install -g @openapitools/openapi-generator-cli
fi

# Determine spec source (local file or remote)
SPEC_SOURCE="$OPENAPI_FILE"
if [ ! -f "$SPEC_SOURCE" ]; then
  echo "⚠️  Local spec not found, using remote..."
  SPEC_SOURCE="$OPENAPI_URL"
fi

echo "📋 Using spec: $SPEC_SOURCE"
echo ""

# Generate client
openapi-generator-cli generate \
  -i "$SPEC_SOURCE" \
  -g "$GENERATOR" \
  -o "$OUTPUT_DIR" \
  -p packageName="$PACKAGE_NAME" \
  -p packageVersion="$PACKAGE_VERSION" \
  --skip-validate-spec

echo ""
echo "✅ Client generated successfully!"
echo ""
echo "📁 Generated files:"
ls -la "$OUTPUT_DIR" | grep -v "^d" | awk '{print "   " $NF}'
echo ""

# Language-specific instructions
case $LANGUAGE in
  typescript|ts)
    echo "📚 TypeScript Setup:"
    echo "   cd $OUTPUT_DIR"
    echo "   npm install"
    echo "   npm run build"
    echo ""
    echo "📖 Usage:"
    echo "   import { DefaultApi } from '$OUTPUT_DIR';"
    echo "   const api = new DefaultApi({ basePath: 'http://localhost:3000' });"
    echo "   const job = await api.simulate({ query: '...', parameters: {...} });"
    ;;
  python|py)
    echo "📚 Python Setup:"
    echo "   cd $OUTPUT_DIR"
    echo "   pip install -e ."
    echo ""
    echo "📖 Usage:"
    echo "   from openapi_client import ApiClient, DefaultApi"
    echo "   api = DefaultApi(ApiClient())"
    echo "   job = api.simulate({'query': '...', 'parameters': {...}})"
    ;;
  go)
    echo "📚 Go Setup:"
    echo "   cd $OUTPUT_DIR"
    echo "   go mod init github.com/yourusername/caterva-client"
    echo "   go build ./..."
    echo ""
    echo "📖 Usage:"
    echo "   import \"./generated-go-client\""
    echo "   client := swagger.NewAPIClient(cfg)"
    echo "   job, _, _ := client.DefaultApi.Simulate(ctx, request)"
    ;;
  rust)
    echo "📚 Rust Setup:"
    echo "   cd $OUTPUT_DIR"
    echo "   cargo build"
    echo ""
    echo "📖 Usage:"
    echo "   use openapi_client::apis::default_api::*;"
    echo "   let job = simulate(&config, request).await;"
    ;;
  java)
    echo "📚 Java Setup:"
    echo "   cd $OUTPUT_DIR"
    echo "   mvn clean package"
    echo ""
    echo "📖 Usage:"
    echo "   import com.caterva.client.api.DefaultApi;"
    echo "   DefaultApi api = new DefaultApi();"
    echo "   Job job = api.simulate(request);"
    ;;
esac

echo ""
echo "🎉 Done! Start using your generated client."
