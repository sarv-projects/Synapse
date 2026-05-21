#!/usr/bin/env python3
"""
Interactive Source Configuration Generator for SYNAPSE
Automatically tests URLs and generates YAML configurations using Groq AI.
"""

import asyncio
import json
import sys
import yaml
from typing import Dict, Any, Optional, List
import httpx
from urllib.parse import urlparse
import re

from groq import Groq
from schema.config import get_settings


class SourceConfigGenerator:
    """Interactive tool to generate source configurations automatically."""
    
    def __init__(self):
        self.settings = get_settings()
        self.groq_client = Groq(api_key=self.settings.groq_api_key)
        self.http_client = httpx.Client(timeout=10.0)
        
        # Available source types
        self.source_types = {
            "1": "rest_json",
            "2": "rest_xml", 
            "3": "rss",
            "4": "github_rss"
        }
        
        # Common entity types
        self.entity_types = [
            "Paper", "Model", "Tool", "Technique", "Author", 
            "Organization", "Benchmark", "Dataset", "Space"
        ]
    
    async def run_interactive_generator(self):
        """Run the interactive configuration generator."""
        print("🚀 SYNAPSE Source Configuration Generator")
        print("=" * 50)
        print("This tool helps you automatically generate source configurations")
        print("by testing URLs and using AI to analyze the API structure.\n")
        
        try:
            # Get URL from user
            url = self._get_user_input_url()
            
            # Test URL connectivity and analyze response
            print(f"\n🔍 Testing URL: {url}")
            analysis = await self._test_and_analyze_url(url)
            
            if not analysis["accessible"]:
                print(f"❌ Failed to access URL: {analysis['error']}")
                return
            
            print(f"✅ URL accessible! Status: {analysis['status_code']}")
            print(f"📄 Content type: {analysis['content_type']}")
            print(f"📊 Response size: {analysis['content_length']} bytes\n")
            
            # Get source type preference
            source_type = self._get_source_type_preference(analysis)
            
            # Get entity types
            entities = self._get_entity_types()
            
            # Generate configuration using AI
            print(f"\n🤖 Generating configuration using {self.settings.groq_model}...")
            config = await self._generate_config_with_ai(
                url, source_type, entities, analysis
            )
            
            if config:
                # Display and save configuration
                self._display_and_save_config(config, url)
            else:
                print("❌ Failed to generate configuration")
                
        except KeyboardInterrupt:
            print("\n\n👋 Generator cancelled by user")
        except Exception as e:
            print(f"\n❌ Error: {e}")
        finally:
            self.http_client.close()
    
    def _get_user_input_url(self) -> str:
        """Get URL input from user with validation."""
        while True:
            url = input("📍 Enter the source URL: ").strip()
            
            if not url:
                print("❌ URL cannot be empty")
                continue
            
            # Add protocol if missing
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Basic URL validation
            try:
                parsed = urlparse(url)
                if not parsed.netloc:
                    print("❌ Invalid URL format")
                    continue
                return url
            except Exception:
                print("❌ Invalid URL format")
                continue
    
    async def _test_and_analyze_url(self, url: str) -> Dict[str, Any]:
        """Test URL accessibility and analyze response."""
        try:
            response = self.http_client.get(url)
            
            analysis = {
                "accessible": True,
                "status_code": response.status_code,
                "content_type": response.headers.get('content-type', 'unknown'),
                "content_length": len(response.content),
                "response_text": response.text[:2000],  # First 2KB for analysis
                "headers": dict(response.headers),
                "error": None
            }
            
            # Detect format from content type
            content_type = analysis["content_type"].lower()
            if 'json' in content_type:
                analysis["detected_format"] = "json"
            elif 'xml' in content_type or 'atom' in content_type:
                analysis["detected_format"] = "xml"
            elif 'rss' in content_type:
                analysis["detected_format"] = "rss"
            else:
                analysis["detected_format"] = "unknown"
            
            return analysis
            
        except Exception as e:
            return {
                "accessible": False,
                "error": str(e),
                "status_code": None,
                "content_type": None,
                "content_length": 0,
                "response_text": None,
                "headers": None,
                "detected_format": None
            }
    
    def _get_source_type_preference(self, analysis: Dict[str, Any]) -> str:
        """Get source type preference from user with AI suggestion."""
        detected = analysis.get("detected_format", "unknown")
        
        print(f"\n📋 Detected format: {detected}")
        print("Available source types:")
        for key, value in self.source_types.items():
            print(f"  {key}. {value}")
        
        # Suggest based on detection
        suggestion = None
        if detected == "json":
            suggestion = "1"  # rest_json
        elif detected in ["xml", "rss"]:
            suggestion = "2" if "xml" in detected else "3"
        
        if suggestion:
            print(f"\n💡 Suggestion: {suggestion} ({self.source_types[suggestion]})")
        
        while True:
            choice = input(f"\n🎯 Choose source type (1-{len(self.source_types)}): ").strip()
            if choice in self.source_types:
                return self.source_types[choice]
            print("❌ Invalid choice")
    
    def _get_entity_types(self) -> List[str]:
        """Get entity types from user."""
        print(f"\n🏷️  Available entity types:")
        for i, entity in enumerate(self.entity_types, 1):
            print(f"  {i}. {entity}")
        
        while True:
            input_str = input("\n🎯 Enter entity numbers (comma-separated, e.g., 1,3,5): ").strip()
            try:
                indices = [int(x.strip()) - 1 for x in input_str.split(',')]
                entities = []
                for idx in indices:
                    if 0 <= idx < len(self.entity_types):
                        entities.append(self.entity_types[idx])
                    else:
                        raise ValueError("Invalid index")
                
                if entities:
                    return entities
                else:
                    print("❌ Please select at least one entity type")
            except (ValueError, IndexError):
                print("❌ Invalid input. Use numbers like: 1,3,5")
    
    async def _generate_config_with_ai(
        self, 
        url: str, 
        source_type: str, 
        entities: List[str],
        analysis: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Generate configuration using Groq AI."""
        
        prompt = f"""You are an expert at API configuration for a knowledge graph ingestion system.

TASK: Generate a YAML configuration for a data source.

URL: {url}
Source Type: {source_type}
Entity Types: {', '.join(entities)}
Content Type: {analysis['content_type']}
Detected Format: {analysis['detected_format']}

Sample Response (first 1000 chars):
{analysis['response_text'][:1000]}

RESPONSE HEADERS:
{json.dumps(analysis['headers'], indent=2)}

Generate a YAML configuration following this exact structure:

name: [short_descriptive_name]
type: {source_type}
base_url: {url}
rate_limit:
  requests_per_hour: [reasonable_number]
auth_required: [true/false]
entity_coverage:
  - [list the entities]
fetch_params:
  [relevant_parameters based on the API]

RULES:
1. Name should be short, lowercase, with underscores
2. Rate limit should be reasonable for the API
3. Include relevant fetch_params if the API supports filtering/pagination
4. Set auth_required=true if authentication seems needed
5. Output ONLY valid YAML, no explanations

Generate the configuration:"""

        try:
            response = self.groq_client.chat.completions.create(
                model=self.settings.groq_model,
                messages=[
                    {"role": "system", "content": "You are an API configuration expert. Generate only valid YAML."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.1
            )
            
            yaml_content = response.choices[0].message.content.strip()
            
            # Clean up the response
            yaml_content = re.sub(r'```yaml\s*', '', yaml_content)
            yaml_content = re.sub(r'```\s*$', '', yaml_content)
            yaml_content = yaml_content.strip()
            
            # Parse YAML to validate
            try:
                config = yaml.safe_load(yaml_content)
                return config
            except yaml.YAMLError as e:
                print(f"⚠️  AI generated invalid YAML: {e}")
                print("🔄 Trying to fix common issues...")
                
                # Try to fix common YAML issues
                fixed_yaml = self._fix_yaml_issues(yaml_content)
                try:
                    config = yaml.safe_load(fixed_yaml)
                    return config
                except yaml.YAMLError:
                    print("❌ Could not fix YAML format")
                    return None
                    
        except Exception as e:
            print(f"❌ AI generation failed: {e}")
            return None
    
    def _fix_yaml_issues(self, yaml_content: str) -> str:
        """Fix common YAML formatting issues."""
        # Fix indentation issues
        lines = yaml_content.split('\n')
        fixed_lines = []
        
        for line in lines:
            # Fix common quoting issues
            if ':' in line and not line.strip().startswith('-'):
                key, value = line.split(':', 1)
                value = value.strip()
                
                # Quote values that might need it
                if value and not (value.startswith('"') or value.startswith("'")):
                    if any(char in value for char in ['[', ']', '{', '}', ':', '#', '@', '`', '|', '>', '*', '&']):
                        value = f'"{value}"'
                
                line = f"{key}: {value}"
            
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def _display_and_save_config(self, config: Dict[str, Any], url: str):
        """Display and save the generated configuration."""
        print("\n✅ Configuration Generated!")
        print("=" * 50)
        
        # Display configuration
        yaml_str = yaml.dump(config, default_flow_style=False, indent=2)
        print(yaml_str)
        
        # Save to file
        filename = f"source_{config.get('name', 'generated')}.yaml"
        filepath = f"scripts/{filename}"
        
        try:
            with open(filepath, 'w') as f:
                f.write(f"# Auto-generated configuration for: {url}\n")
                f.write(f"# Generated on: {asyncio.get_event_loop().time()}\n")
                f.write(yaml_str)
            
            print(f"\n💾 Configuration saved to: {filepath}")
            print(f"\n📋 Next steps:")
            print(f"1. Review the configuration")
            print(f"2. Add it to domains/ai/sources.yaml")
            print(f"3. Test with: python -m ingestion.source_factory")
            
        except Exception as e:
            print(f"❌ Failed to save configuration: {e}")
            print(f"\n📋 Manual copy:")
            print(yaml_str)


async def main():
    """Main entry point."""
    generator = SourceConfigGenerator()
    await generator.run_interactive_generator()


if __name__ == "__main__":
    # Check for Groq API key
    settings = get_settings()
    if not settings.groq_api_key:
        print("❌ GROQ_API_KEY environment variable is required")
        print("Please set it in your .env file")
        sys.exit(1)
    
    asyncio.run(main())
