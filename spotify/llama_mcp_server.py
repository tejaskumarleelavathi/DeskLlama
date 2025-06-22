#!/usr/bin/env python3
"""
MCP Server for Spotify that can work with Llama-based assistants
This is a more advanced implementation following MCP protocol
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from pydantic import BaseModel
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy import SpotifyException

class SpotifyMCPServer:
    def __init__(self):
        self.server = Server("llama-spotify-mcp")
        self.setup_spotify()
        self.setup_handlers()
    
    def setup_spotify(self):
        """Initialize Spotify client"""
        client_id = os.getenv('SPOTIFY_CLIENT_ID')
        client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        redirect_uri = os.getenv('SPOTIFY_REDIRECT_URI', 'http://localhost:8080/callback')
        
        if not client_id or not client_secret:
            raise ValueError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set")
        
        scope = "user-read-playback-state,user-modify-playback-state,user-read-currently-playing,playlist-read-private,playlist-modify-public,playlist-modify-private"
        
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope
        ))
    
    def setup_handlers(self):
        """Setup MCP handlers"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """List available Spotify tools"""
            return [
                types.Tool(
                    name="get_current_playback",
                    description="Get information about currently playing track",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="play_pause",
                    description="Toggle play/pause of current track",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="skip_track",
                    description="Skip to the next track",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="previous_track",
                    description="Go to the previous track",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                types.Tool(
                    name="search_and_play",
                    description="Search for and play music",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "type": {"type": "string", "enum": ["track", "album", "playlist"], "default": "track"}
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="set_volume",
                    description="Set the volume level (0-100)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "volume": {"type": "integer", "minimum": 0, "maximum": 100}
                        },
                        "required": ["volume"]
                    }
                ),
                types.Tool(
                    name="get_playlists",
                    description="Get user's Spotify playlists",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}
                        },
                        "required": []
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.TextContent]:
            """Handle tool calls"""
            try:
                if name == "get_current_playback":
                    result = self.get_current_playback()
                elif name == "play_pause":
                    result = self.play_pause()
                elif name == "skip_track":
                    result = self.skip_track()
                elif name == "previous_track":
                    result = self.previous_track()
                elif name == "search_and_play":
                    result = self.search_and_play(
                        arguments.get("query", ""),
                        arguments.get("type", "track")
                    )
                elif name == "set_volume":
                    result = self.set_volume(arguments.get("volume", 50))
                elif name == "get_playlists":
                    result = self.get_playlists(arguments.get("limit", 10))
                else:
                    result = {"error": f"Unknown tool: {name}"}
                
                return [types.TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )]
                
            except SpotifyException as e:
                return [types.TextContent(
                    type="text",
                    text=f"Spotify error: {str(e)}"
                )]
            except Exception as e:
                return [types.TextContent(
                    type="text",
                    text=f"Error: {str(e)}"
                )]
    
    def get_current_playback(self) -> Dict[str, Any]:
        """Get current playback information"""
        current = self.sp.current_playback()
        if current and current.get('item'):
            return {
                'track': current['item']['name'],
                'artist': ', '.join([artist['name'] for artist in current['item']['artists']]),
                'album': current['item']['album']['name'],
                'is_playing': current['is_playing'],
                'progress_ms': current['progress_ms'],
                'duration_ms': current['item']['duration_ms'],
                'device': current['device']['name'] if current.get('device') else 'Unknown'
            }
        return {'status': 'No active playback'}
    
    def play_pause(self) -> Dict[str, str]:
        """Toggle play/pause"""
        current = self.sp.current_playback()
        if current and current['is_playing']:
            self.sp.pause_playback()
            return {'status': 'Paused'}
        else:
            self.sp.start_playback()
            return {'status': 'Playing'}
    
    def skip_track(self) -> Dict[str, str]:
        """Skip to next track"""
        self.sp.next_track()
        return {'status': 'Skipped to next track'}
    
    def previous_track(self) -> Dict[str, str]:
        """Go to previous track"""
        self.sp.previous_track()
        return {'status': 'Went to previous track'}
    
    def search_and_play(self, query: str, result_type: str = 'track') -> Dict[str, Any]:
        """Search for music and play first result"""
        results = self.sp.search(q=query, type=result_type, limit=1)
        
        if result_type == 'track' and results['tracks']['items']:
            track = results['tracks']['items'][0]
            self.sp.start_playback(uris=[track['uri']])
            return {
                'status': f'Now playing: {track["name"]} by {", ".join([artist["name"] for artist in track["artists"]])}'
            }
        elif result_type == 'album' and results['albums']['items']:
            album = results['albums']['items'][0]
            self.sp.start_playback(context_uri=album['uri'])
            return {
                'status': f'Now playing album: {album["name"]} by {", ".join([artist["name"] for artist in album["artists"]])}'
            }
        elif result_type == 'playlist' and results['playlists']['items']:
            playlist = results['playlists']['items'][0]
            self.sp.start_playback(context_uri=playlist['uri'])
            return {
                'status': f'Now playing playlist: {playlist["name"]}'
            }
        else:
            return {'error': f'No {result_type} found for: {query}'}
    
    def set_volume(self, volume: int) -> Dict[str, str]:
        """Set volume (0-100)"""
        volume = max(0, min(100, volume))
        self.sp.volume(volume)
        return {'status': f'Volume set to {volume}%'}
    
    def get_playlists(self, limit: int = 10) -> Dict[str, Any]:
        """Get user's playlists"""
        playlists = self.sp.current_user_playlists(limit=limit)
        playlist_list = []
        for playlist in playlists['items']:
            playlist_list.append({
                'name': playlist['name'],
                'id': playlist['id'],
                'tracks': playlist['tracks']['total'],
                'public': playlist['public']
            })
        return {'playlists': playlist_list}
    
    async def run(self):
        """Run the MCP server"""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )

class LlamaMCPClient:
    """
    A simple client that can connect to the MCP server
    This simulates how a Llama-based assistant would interact with the MCP server
    """
    def __init__(self, llama_api_key: str):
        self.llama_api_key = llama_api_key
        # In a real implementation, you'd connect to the MCP server here
        
    async def send_command(self, command: str) -> str:
        """
        Send a command to Llama and get the MCP tool calls
        This is a simplified version - in reality, you'd need proper MCP protocol handling
        """
        # This would involve:
        # 1. Sending the command to Llama
        # 2. Llama analyzing the command and deciding which tools to call
        # 3. Making the actual MCP tool calls
        # 4. Getting results and having Llama format a response
        
        return "This would integrate with your Llama API and MCP protocol"

def main():
    """Main entry point for the MCP server"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Llama-Spotify MCP Server")
    parser.add_argument("--mode", choices=["server", "client"], default="server",
                       help="Run as MCP server or test client")
    args = parser.parse_args()
    
    if args.mode == "server":
        # Run as MCP server
        try:
            server = SpotifyMCPServer()
            print("Starting Llama-Spotify MCP Server...", file=sys.stderr)
            asyncio.run(server.run())
        except KeyboardInterrupt:
            print("Server stopped", file=sys.stderr)
        except Exception as e:
            print(f"Server error: {e}", file=sys.stderr)
            sys.exit(1)
    
    else:
        # Run as test client (for debugging)
        print("MCP Client mode - this would connect to a Llama API")
        print("In a real implementation, this would:")
        print("1. Connect to Llama API")
        print("2. Send user commands to Llama")
        print("3. Let Llama decide which MCP tools to call")
        print("4. Execute the tools and return results")

if __name__ == "__main__":
    main()