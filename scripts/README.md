# SYNAPSE Source Configuration Generator

This tool makes it incredibly easy to add new data sources to SYNAPSE by automatically testing URLs and generating YAML configurations using AI.

## 🚀 Quick Start

### Method 1: Interactive Generator (Recommended)

```bash
# Make sure you're in the SYNAPSE root directory
cd /path/to/nexus

# Set your Groq API key
export GROQ_API_KEY=your_groq_api_key_here

# Run the interactive generator
python scripts/source_config_generator.py
```

### Method 2: Shell Script

```bash
# Run the helper script
./scripts/add_source.sh
```

## 🎯 What It Does

1. **URL Testing**: Automatically tests if the URL is accessible
2. **Format Detection**: Analyzes response to detect JSON/XML/RSS format
3. **AI Analysis**: Uses Groq Llama 4 Scout to analyze the API structure
4. **Smart Configuration**: Generates optimal YAML configuration
5. **Validation**: Validates and fixes common YAML formatting issues

## 📋 Interactive Flow

The generator will ask for:

1. **URL**: The API endpoint or feed URL
2. **Source Type**: Choose from:
   - `rest_json` - REST APIs returning JSON
   - `rest_xml` - REST APIs returning XML (like arXiv)
   - `rss` - RSS/Atom feeds
   - `github_rss` - GitHub-specific RSS feeds

3. **Entity Types**: What data to extract (choose multiple):
   - Paper, Model, Tool, Technique, Author, Organization, Benchmark, Dataset, Space

## 🤖 AI-Powered Features

The Groq AI analyzes:
- Response headers and content type
- Sample response data
- API patterns and structure
- Rate limiting requirements
- Authentication needs

## 📄 Example Usage

```
🚀 SYNAPSE Source Configuration Generator
==================================================
This tool helps you automatically generate source configurations
by testing URLs and using AI to analyze the API structure.

📍 Enter the source URL: https://api.example.com/papers

🔍 Testing URL: https://api.example.com/papers
✅ URL accessible! Status: 200
📄 Content type: application/json
📊 Response size: 15420 bytes

📋 Detected format: json
Available source types:
  1. rest_json
  2. rest_xml
  3. rss
  4. github_rss

💡 Suggestion: 1 (rest_json)

🎯 Choose source type (1-4): 1

🏷️  Available entity types:
  1. Paper
  2. Model
  3. Tool
  4. Technique
  5. Author
  6. Organization
  7. Benchmark
  8. Dataset
  9. Space

🎯 Enter entity numbers (comma-separated, e.g., 1,3,5): 1,5

🤖 Generating configuration using llama-4-scout-17b...

✅ Configuration Generated!
==================================================
name: example_papers_api
type: rest_json
base_url: https://api.example.com/papers
rate_limit:
  requests_per_hour: 1000
auth_required: false
entity_coverage:
  - Paper
  - Author
fetch_params:
  limit: 100
  sort: created_at

💾 Configuration saved to: scripts/source_example_papers_api.yaml

📋 Next steps:
1. Review the configuration
2. Add it to domains/ai/sources.yaml
3. Test with: python -m ingestion.source_factory
```

## 🔧 Requirements

- **Groq API Key**: Set `GROQ_API_KEY` environment variable
- **Python 3.8+**: With required dependencies installed
- **Internet Access**: For testing URLs and calling Groq API

## 📁 Generated Files

The tool saves generated configurations as:
```
scripts/source_<name>.yaml
```

Each file includes:
- Auto-generated YAML configuration
- Source URL comment
- Generation timestamp

## 🔄 Integration Steps

1. **Generate Configuration**: Run the tool
2. **Review**: Check the generated YAML file
3. **Add to Sources**: Copy to `domains/ai/sources.yaml`
4. **Test**: Verify with the source factory
5. **Deploy**: Include in next pipeline run

## 🛠️ Advanced Usage

### Manual Testing

You can test URLs manually:

```python
from scripts.source_config_generator import SourceConfigGenerator
import asyncio

generator = SourceConfigGenerator()
analysis = await generator._test_and_analyze_url("https://api.example.com")
print(analysis)
```

### Batch Processing

For multiple URLs, modify the script to process them in batch.

## 🐛 Troubleshooting

### Common Issues

1. **Groq API Key Missing**
   ```
   ❌ GROQ_API_KEY environment variable is required
   ```
   Solution: Set the environment variable

2. **URL Not Accessible**
   ```
   ❌ Failed to access URL: Connection timeout
   ```
   Solution: Check URL, network, or API status

3. **Invalid YAML**
   ```
   ⚠️ AI generated invalid YAML
   ```
   Solution: Tool attempts auto-fix, but manual review may be needed

### Debug Mode

Add debug prints to see the AI analysis:

```python
# In source_config_generator.py
print(f"Raw AI response: {response.choices[0].message.content}")
```

## 📚 Supported Source Types

| Type | Description | Examples |
|------|-------------|----------|
| `rest_json` | REST APIs with JSON responses | Modern APIs, most web services |
| `rest_xml` | REST APIs with XML responses | arXiv, legacy systems |
| `rss` | RSS/Atom feeds | Blogs, news sites |
| `github_rss` | GitHub-specific RSS feeds | GitHub trending, releases |

## 🎉 Benefits

- **Zero Code**: Add sources without writing Python
- **Smart Detection**: AI analyzes API structure automatically  
- **Best Practices**: Generates optimal configurations
- **Validation**: Tests URLs and validates YAML
- **Fast**: Add new sources in under 2 minutes

## 🤝 Contributing

To add support for new source types:
1. Update `source_types` in the generator
2. Add detection logic in `_test_and_analyze_url`
3. Update the AI prompt with new patterns
