#!/bin/bash
# Quick script to add a new source to SYNAPSE

echo "🚀 SYNAPSE Source Adder"
echo "======================"

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ] || [ ! -d "domains" ]; then
    echo "❌ Please run this script from the SYNAPSE root directory"
    exit 1
fi

# Check for Groq API key
if [ -z "$GROQ_API_KEY" ]; then
    echo "❌ GROQ_API_KEY environment variable is required"
    echo "Please set it in your .env file or export it:"
    echo "export GROQ_API_KEY=your_key_here"
    exit 1
fi

# Run the generator
echo "🤖 Starting source configuration generator..."
python3 scripts/source_config_generator.py

echo ""
echo "✅ Done! Check the generated YAML file and add it to domains/ai/sources.yaml"
