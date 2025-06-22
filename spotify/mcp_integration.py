#!/usr/bin/env python3
"""
Pure MCP Integration for Llama-Spotify Control
Works with the Node.js spotify-mcp-server
"""

import asyncio
import json
import os
import subprocess
import sys
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

class PureMCPSpotifyClient:
    """
    Pure MCP client that properly communicates with the Node.js spotify-mcp-server
    """
    
    def __init__(self, llama_api_key: str, spotify_mcp_path: str, llama_model: str = "Llama-4-Maverick-17B-128E-Instruct-FP8"):
        self.llama_api_key = llama_api_key
        self.model = llama_model
        self.llama_endpoint = "https://api.llama.com/v1/chat/completions"
        self.spotify_mcp_path = spotify_mcp_path
        self.mcp_process = None
        self.next_id = 1
        self.tools = []
        self.initialized = False
        
    def get_next_id(self) -> int:
        """Get unique ID for JSON-RPC requests"""
        current_id = self.next_id
        self.next_id += 1
        return current_id
        
    async def start_mcp_server(self):
        """Start the Node.js MCP server"""
        try:
            # Check if the MCP server path exists
            if not os.path.exists(self.spotify_mcp_path):
                print(f"❌ MCP server not found at: {self.spotify_mcp_path}")
                print("Please make sure you've cloned and built the spotify-mcp-server")
                return False
            
            print(f"🔄 Starting MCP server: node {self.spotify_mcp_path}")
            
            # Start the Node.js MCP server
            self.mcp_process = await asyncio.create_subprocess_exec(
                "node", self.spotify_mcp_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(self.spotify_mcp_path)
            )
            
            # Start stderr reader task
            asyncio.create_task(self._read_stderr())
            
            print("✅ MCP Server process started")
            
            # Wait a moment for server to initialize
            await asyncio.sleep(2)
            
            # Initialize the MCP connection
            if await self.initialize_mcp():
                print("✅ MCP initialization complete")
                return True
            else:
                print("❌ MCP initialization failed")
                return False
                
        except FileNotFoundError:
            print("❌ Node.js not found. Please install Node.js")
            return False
        except Exception as e:
            print(f"❌ Failed to start MCP server: {e}")
            return False
    
    async def _read_stderr(self):
        """Read and log stderr from MCP server"""
        if not self.mcp_process or not self.mcp_process.stderr:
            return
            
        try:
            while True:
                line = await self.mcp_process.stderr.readline()
                if not line:
                    break
                error_msg = line.decode().strip()
                if error_msg:
                    print(f"🔧 MCP Server: {error_msg}")
        except Exception as e:
            print(f"Error reading MCP stderr: {e}")
    
    async def send_mcp_request(self, method: str, params: Any = None, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """Send a JSON-RPC request to the MCP server with timeout"""
        if not self.mcp_process:
            return None
            
        request = {
            "jsonrpc": "2.0",
            "id": self.get_next_id(),
            "method": method
        }
        
        if params is not None:
            request["params"] = params
            
        try:
            # Send request
            request_str = json.dumps(request) + "\n"
            print(f"🔧 Sending MCP request: {request_str.strip()}")
            
            if not self.mcp_process.stdin:
                print("❌ MCP stdin not available")
                return None
                
            self.mcp_process.stdin.write(request_str.encode())
            await self.mcp_process.stdin.drain()
            
            # Read response with timeout
            try:
                response_line = await asyncio.wait_for(
                    self.mcp_process.stdout.readline(), 
                    timeout=timeout
                )
                
                if response_line:
                    response_text = response_line.decode().strip()
                    if response_text:
                        response = json.loads(response_text)
                        print(f"🔧 MCP response: {json.dumps(response, indent=2)}")
                        
                        # Handle errors
                        if "error" in response:
                            print(f"❌ MCP Error: {response['error']}")
                            return None
                            
                        return response
                    
            except asyncio.TimeoutError:
                print(f"❌ MCP request timed out after {timeout}s")
                return None
                
            return None
            
        except Exception as e:
            print(f"❌ MCP communication error: {e}")
            return None
    
    async def send_mcp_notification(self, method: str, params: Any = None):
        """Send a JSON-RPC notification to the MCP server"""
        if not self.mcp_process or not self.mcp_process.stdin:
            return
            
        notification = {
            "jsonrpc": "2.0",
            "method": method
        }
        
        if params is not None:
            notification["params"] = params
            
        try:
            # Send notification
            notification_str = json.dumps(notification) + "\n"
            print(f"🔧 Sending MCP notification: {notification_str.strip()}")
            
            self.mcp_process.stdin.write(notification_str.encode())
            await self.mcp_process.stdin.drain()
        except Exception as e:
            print(f"❌ MCP notification error: {e}")
    
    async def initialize_mcp(self) -> bool:
        """Initialize MCP connection with proper handshake"""
        try:
            # Step 1: Send initialize request
            init_params = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "clientInfo": {
                    "name": "llama-spotify-client",
                    "version": "1.0.0"
                }
            }
            
            response = await self.send_mcp_request("initialize", init_params, timeout=15.0)
            if response and ("result" in response or response.get("id")):
                print(f"🤝 MCP handshake successful")
                
                # Step 2: Send initialized notification
                await self.send_mcp_notification("notifications/initialized")
                
                # Wait a moment for the server to process
                await asyncio.sleep(1)
                
                # Step 3: List available tools
                tools_response = await self.send_mcp_request("tools/list", timeout=10.0)
                if tools_response and "result" in tools_response:
                    result = tools_response["result"]
                    if "tools" in result:
                        self.tools = result["tools"]
                    else:
                        # Handle case where result might be the tools array directly
                        self.tools = result if isinstance(result, list) else []
                    
                    print(f"📋 Found {len(self.tools)} MCP tools: {[tool['name'] for tool in self.tools]}")
                    
                    # Print tool details for debugging
                    for tool in self.tools:
                        print(f"   - {tool['name']}: {tool.get('description', 'No description')}")
                    
                    self.initialized = True
                    return True
                else:
                    print("❌ Failed to list tools")
                    return False
                
            else:
                print("❌ MCP handshake failed")
                return False
                
        except Exception as e:
            print(f"❌ MCP initialization error: {e}")
            return False
    
    async def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call an MCP tool using proper protocol"""
        if not self.initialized:
            print("❌ MCP not initialized")
            return {"error": "MCP not initialized"}
        
        # Check if tool exists
        tool_exists = any(tool["name"] == tool_name for tool in self.tools)
        if not tool_exists:
            available_tools = [tool["name"] for tool in self.tools]
            print(f"❌ Tool '{tool_name}' not found. Available tools: {available_tools}")
            return {"error": f"Tool '{tool_name}' not available. Available: {available_tools}"}
        
        # Call the tool
        params = {
            "name": tool_name,
            "arguments": arguments
        }
        
        print(f"🔧 Calling MCP tool '{tool_name}' with arguments: {json.dumps(arguments, indent=2)}")
        
        response = await self.send_mcp_request("tools/call", params, timeout=30.0)
        if response and "result" in response:
            result = response["result"]
            print(f"🔧 Raw MCP tool result: {json.dumps(result, indent=2)}")
            
            # Handle the Node.js MCP server response format
            if isinstance(result, dict):
                if "content" in result:
                    # Standard MCP response format
                    content = result["content"]
                    if isinstance(content, list) and len(content) > 0:
                        first_content = content[0]
                        if isinstance(first_content, dict):
                            if first_content.get("type") == "text":
                                text = first_content.get("text", "")
                                try:
                                    return json.loads(text)
                                except json.JSONDecodeError:
                                    return {"status": text}
                            else:
                                return first_content
                    return {"status": str(content)}
                else:
                    # Direct result
                    return result
            elif isinstance(result, list) and len(result) > 0:
                # Handle list response
                first_item = result[0]
                if isinstance(first_item, dict) and first_item.get("type") == "text":
                    text = first_item.get("text", "")
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return {"status": text}
                return {"status": str(result)}
            else:
                return {"status": str(result)}
        
        error_msg = f"MCP tool call failed for {tool_name}"
        if response and "error" in response:
            error_msg += f": {response['error']}"
        
        return {"error": error_msg}
    
    def call_llama_api(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call the Llama API with function calling support"""
        headers = {
            "Authorization": f"Bearer {self.llama_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1000
        }
        
        # Add tools if provided
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        try:
            print(f"DEBUG: Calling Llama API with {len(tools) if tools else 0} tools")
            response = requests.post(self.llama_endpoint, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            print(f"DEBUG: Llama API response status: {response.status_code}")
            
            # Handle Llama API response format
            if "completion_message" in result:
                completion_msg = result["completion_message"]
                
                # Extract content
                content = completion_msg.get("content", "")
                if isinstance(content, dict):
                    content = content.get("text", "")
                elif not isinstance(content, str):
                    content = str(content)
                
                # Extract tool calls
                tool_calls = completion_msg.get("tool_calls", [])
                
                return {
                    "content": content,
                    "tool_calls": tool_calls
                }
            
            else:
                print(f"DEBUG: Unexpected Llama response format")
                return {
                    "content": "I'll help you with that request.", 
                    "tool_calls": []
                }
                
        except requests.exceptions.Timeout:
            print("❌ Llama API request timed out")
            return {
                "content": "Request timed out. Please try again.", 
                "tool_calls": []
            }
        except Exception as e:
            print(f"❌ Llama API call failed: {e}")
            return {
                "content": f"Error calling Llama API: {str(e)}", 
                "tool_calls": []
            }
    
    def convert_mcp_tools_to_llama_format(self) -> List[Dict[str, Any]]:
        """Convert MCP tools to Llama API format with proper parameter mapping"""
        llama_tools = []
        
        # Mapping of MCP tool names to their expected parameters
        tool_mappings = {
            "searchSpotify": {
                "name": "searchSpotify",
                "description": "Search for tracks, albums, artists, or playlists on Spotify",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search term"},
                        "type": {"type": "string", "enum": ["track", "album", "artist", "playlist"], "description": "Type of item to search for"},
                        "limit": {"type": "number", "minimum": 1, "maximum": 50, "default": 10, "description": "Maximum number of results"}
                    },
                    "required": ["query", "type"]
                }
            },
            "playMusic": {
                "name": "playMusic", 
                "description": "Start playing a track, album, artist, or playlist on Spotify",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "uri": {"type": "string", "description": "Spotify URI of the item to play"},
                        "type": {"type": "string", "enum": ["track", "album", "artist", "playlist"], "description": "Type of item to play"},
                        "id": {"type": "string", "description": "Spotify ID of the item to play"},
                        "deviceId": {"type": "string", "description": "ID of the device to play on"}
                    }
                }
            },
            "getNowPlaying": {
                "name": "getNowPlaying",
                "description": "Get information about the currently playing track on Spotify", 
                "parameters": {"type": "object", "properties": {}}
            },
            "pausePlayback": {
                "name": "pausePlayback",
                "description": "Pause the currently playing track on Spotify",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "deviceId": {"type": "string", "description": "ID of the device to pause"}
                    }
                }
            },
            "skipToNext": {
                "name": "skipToNext",
                "description": "Skip to the next track in the current playback queue",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "deviceId": {"type": "string", "description": "ID of the device"}
                    }
                }
            },
            "skipToPrevious": {
                "name": "skipToPrevious", 
                "description": "Skip to the previous track in the current playback queue",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "deviceId": {"type": "string", "description": "ID of the device"}
                    }
                }
            },
            "getMyPlaylists": {
                "name": "getMyPlaylists",
                "description": "Get a list of the current user's playlists on Spotify",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "number", "minimum": 1, "maximum": 50, "default": 20},
                        "offset": {"type": "number", "minimum": 0, "default": 0}
                    }
                }
            }
        }
        
        for tool in self.tools:
            tool_name = tool["name"]
            
            # Use predefined mapping if available, otherwise use the tool's inputSchema
            if tool_name in tool_mappings:
                llama_tool = {
                    "type": "function",
                    "function": tool_mappings[tool_name]
                }
            else:
                llama_tool = {
                    "type": "function", 
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})
                    }
                }
            
            llama_tools.append(llama_tool)
        
        return llama_tools
    
    async def process_user_command(self, user_input: str) -> str:
        """Process a user command through Llama and MCP"""
        try:
            if not self.initialized:
                return "❌ MCP not initialized. Please restart the application."
            
            # Convert MCP tools to Llama format
            llama_tools = self.convert_mcp_tools_to_llama_format()
            
            # Prepare messages for Llama with detailed instructions
            system_message = f"""You are a helpful assistant that controls Spotify through function calls.

Available functions:
- searchSpotify: Search for music content
- playMusic: Play tracks, albums, artists, or playlists  
- getNowPlaying: Get currently playing track info
- pausePlayback: Pause playback
- skipToNext: Skip to next track
- skipToPrevious: Skip to previous track
- getMyPlaylists: Get user's playlists

When users ask to play music:
1. First use searchSpotify to find the content
2. Then use playMusic with the returned URI or ID

For genre requests like "play jazz music":
- Search with type="playlist" to find curated playlists
- Or search with type="track" for individual tracks

Always prioritize the most appropriate function for the user's request."""

            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_input}
            ]
            
            # Call Llama API
            response = self.call_llama_api(messages, llama_tools)
            
            # Process tool calls if any
            if response.get("tool_calls"):
                results = []
                for tool_call in response["tool_calls"]:
                    try:
                        # Handle the Llama API tool call format
                        if isinstance(tool_call, dict) and "function" in tool_call:
                            tool_name = tool_call["function"]["name"]
                            arguments_str = tool_call["function"]["arguments"]
                        else:
                            tool_name = tool_call.get("name")
                            arguments_str = json.dumps(tool_call.get("arguments", {}))
                        
                        # Parse arguments
                        if isinstance(arguments_str, str):
                            arguments = json.loads(arguments_str)
                        else:
                            arguments = arguments_str
                        
                        print(f"🔧 Calling MCP tool: {tool_name} with args: {arguments}")
                        
                        # Call the MCP tool
                        result = await self.call_mcp_tool(tool_name, arguments)
                        if result and "error" not in result:
                            if "status" in result:
                                status = result["status"]
                            else:
                                status = json.dumps(result, indent=2)
                            results.append(f"✅ {tool_name}: {status}")
                        else:
                            error_msg = result.get('error', 'Unknown error') if result else 'No response'
                            results.append(f"❌ {tool_name}: {error_msg}")
                    
                    except Exception as e:
                        print(f"❌ Error processing tool call: {e}")
                        results.append(f"❌ Tool call error: {str(e)}")
                
                final_response = response.get('content', '') or "I executed the following actions:"
                return f"{final_response}\n\nResults:\n" + "\n".join(results)
            else:
                # No tool calls, just return the content
                content = response.get('content', 'No response from Llama API')
                if not content.strip():
                    content = "I'm ready to help you control Spotify!"
                return content
                
        except Exception as e:
            print(f"❌ Error in process_user_command: {e}")
            return f"❌ Error processing command: {str(e)}"
    
    async def cleanup(self):
        """Clean up resources"""
        if self.mcp_process:
            try:
                # Send a graceful shutdown
                try:
                    await self.send_mcp_notification("notifications/cancelled")
                except:
                    pass
                
                self.mcp_process.terminate()
                await asyncio.wait_for(self.mcp_process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                print("🔧 Force killing MCP server")
                self.mcp_process.kill()
                await self.mcp_process.wait()

class TerminalInterface:
    """Simple terminal interface for testing"""
    
    def __init__(self, llama_api_key: str, spotify_mcp_path: str):
        self.client = PureMCPSpotifyClient(llama_api_key, spotify_mcp_path)
    
    async def run(self):
        """Run the terminal interface"""
        print("🎵 Pure MCP Llama-Spotify Controller")
        print("=" * 60)
        
        # Start MCP server and initialize
        if not await self.client.start_mcp_server():
            print("❌ Failed to start MCP server. Please check your setup.")
            print("\n🔧 Troubleshooting tips:")
            print("1. Make sure you've cloned the repository:")
            print("   git clone https://github.com/marcelmarais/spotify-mcp-server.git")
            print("2. Install dependencies and build:")
            print("   cd spotify-mcp-server && npm install && npm run build")
            print("3. Set up Spotify credentials and authenticate:")
            print("   Copy spotify-config.example.json to spotify-config.json")
            print("   Add your Spotify app credentials")
            print("   Run: npm run auth")
            print("4. Update the MCP_PATH in this script to point to build/index.js")
            return
        
        print("✅ Ready! You can now control Spotify with natural language.")
        print("\n🎵 Available commands:")
        print("  • 'What's currently playing?'")
        print("  • 'Play some jazz music'")
        print("  • 'Skip this song'")
        print("  • 'Pause the music'")
        print("  • 'Show my playlists'")
        print("  • 'Search for Queen songs'")
        print("  • Type 'quit' to exit\n")
        
        try:
            while True:
                user_input = input("🎤 You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    break
                
                if user_input:
                    response = await self.client.process_user_command(user_input)
                    print(f"🤖 Llama: {response}\n")
                    
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
        finally:
            await self.client.cleanup()

def main():
    """Main entry point"""
    llama_api_key = os.getenv('LLAMA_API_KEY')
    
    if not llama_api_key:
        print("❌ LLAMA_API_KEY not found in environment variables")
        print("Please set it in your .env file")
        sys.exit(1)
    
    # Path to the built MCP server - UPDATE THIS PATH
    # Change this to match your actual path to the spotify-mcp-server
    mcp_path = os.path.expanduser("~/spotify-mcp-server/build/index.js")
    
    # You can also set this via environment variable
    mcp_path = os.getenv('SPOTIFY_MCP_PATH', mcp_path)
    
    if not os.path.exists(mcp_path):
        print(f"❌ Spotify MCP server not found at: {mcp_path}")
        print("Please update the SPOTIFY_MCP_PATH or MCP_PATH variable in this script")
        print("It should point to: /path/to/spotify-mcp-server/build/index.js")
        sys.exit(1)
    
    # Run the terminal interface
    interface = TerminalInterface(llama_api_key, mcp_path)
    asyncio.run(interface.run())

if __name__ == "__main__":
    main()