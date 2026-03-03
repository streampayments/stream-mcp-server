"""MCP tools exposing Stream API endpoints from OpenAPI spec.

This module provides tools to query and retrieve API endpoint information
from the Stream OpenAPI specification, making all API endpoints discoverable
and queryable through the MCP server.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


def _load_openapi_spec() -> dict[str, Any]:
    """Load the OpenAPI spec from the local openapi.json file."""
    try:
        import importlib.resources
        
        # Try to load from package resources first
        try:
            files = importlib.resources.files("stream_mcp")
            spec_file = files / ".." / ".." / "openapi.json"
            spec_path = str(spec_file)
        except Exception:
            # Fallback to relative path
            import os
            spec_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "..",
                "openapi.json"
            )
        
        with open(spec_path, "r") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load OpenAPI spec: %s", exc)
        return {}


def _extract_endpoints(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract all endpoints from OpenAPI spec."""
    endpoints = []
    paths = spec.get("paths", {})
    
    for path, methods in paths.items():
        for method, details in methods.items():
            if method.startswith("x-"):  # Skip extensions
                continue
            
            endpoint_info = {
                "path": path,
                "method": method.upper(),
                "summary": details.get("summary", ""),
                "description": details.get("description", ""),
                "operationId": details.get("operationId", ""),
                "tags": details.get("tags", []),
                "parameters": details.get("parameters", []),
                "requestBody": details.get("requestBody"),
                "responses": details.get("responses", {}),
            }
            endpoints.append(endpoint_info)
    
    return endpoints


def _format_endpoint(endpoint: dict[str, Any]) -> str:
    """Format endpoint information as readable text."""
    lines = []
    
    # Header
    lines.append(f"{'='*60}")
    lines.append(f"{endpoint['method']} {endpoint['path']}")
    lines.append(f"{'='*60}")
    
    # Basic info
    if endpoint["summary"]:
        lines.append(f"Summary: {endpoint['summary']}")
    if endpoint["description"]:
        lines.append(f"Description: {endpoint['description']}")
    if endpoint["operationId"]:
        lines.append(f"Operation ID: {endpoint['operationId']}")
    if endpoint["tags"]:
        lines.append(f"Tags: {', '.join(endpoint['tags'])}")
    
    # Parameters
    if endpoint["parameters"]:
        lines.append("\nParameters:")
        for param in endpoint["parameters"]:
            name = param.get("name", "")
            param_in = param.get("in", "")
            required = param.get("required", False)
            schema = param.get("schema", {})
            param_type = schema.get("type", "")
            description = param.get("description", "")
            
            req_str = " (required)" if required else ""
            lines.append(f"  - {name} ({param_in}): {param_type}{req_str}")
            if description:
                lines.append(f"    Description: {description}")
    
    # Request body
    if endpoint["requestBody"]:
        lines.append("\nRequest Body:")
        content = endpoint["requestBody"].get("content", {})
        for content_type in content.keys():
            lines.append(f"  Content-Type: {content_type}")
            schema = content[content_type].get("schema", {})
            if "$ref" in schema:
                lines.append(f"  Schema: {schema['$ref']}")
    
    # Responses
    if endpoint["responses"]:
        lines.append("\nResponses:")
        for status, resp in endpoint["responses"].items():
            lines.append(f"  {status}: {resp.get('description', '')}")
            content = resp.get("content", {})
            for content_type in content.keys():
                schema = content[content_type].get("schema", {})
                if "$ref" in schema:
                    lines.append(f"    Schema: {schema['$ref']}")
    
    return "\n".join(lines)


# ── registration ──────────────────────────────────────────────────────
def register(mcp: FastMCP) -> None:
    """Register API endpoint tools on *mcp*."""
    
    # Load spec once at registration time
    spec = _load_openapi_spec()
    all_endpoints = _extract_endpoints(spec)
    
    @mcp.tool()
    def list_api_endpoints(
        tag: str | None = None,
        method: str | None = None,
        search: str | None = None,
    ) -> str:
        """List all available API endpoints with optional filtering.
        
        Args:
            tag: Filter by endpoint tag (e.g., "Customers", "Invoices")
            method: Filter by HTTP method (GET, POST, PUT, DELETE, etc.)
            search: Search for endpoints by path or summary text
        
        Returns:
            A formatted list of matching endpoints
        """
        endpoints = all_endpoints
        
        # Apply filters
        if method:
            method = method.upper()
            endpoints = [e for e in endpoints if e["method"] == method]
        
        if tag:
            endpoints = [e for e in endpoints if tag in e["tags"]]
        
        if search:
            search_lower = search.lower()
            endpoints = [
                e for e in endpoints
                if search_lower in e["path"].lower()
                or search_lower in e["summary"].lower()
                or search_lower in e["description"].lower()
            ]
        
        if not endpoints:
            return "No endpoints found matching the criteria."
        
        # Format output
        lines = [f"Found {len(endpoints)} endpoint(s):\n"]
        for ep in endpoints:
            lines.append(f"  {ep['method']:6} {ep['path']:40} - {ep['summary']}")
        
        return "\n".join(lines)
    
    @mcp.tool()
    def get_api_endpoint(path: str, method: str = "GET") -> str:
        """Get detailed information about a specific API endpoint.
        
        Args:
            path: The API endpoint path (e.g., "/api/v2/customers")
            method: The HTTP method (GET, POST, PUT, DELETE, PATCH)
        
        Returns:
            Detailed endpoint information including parameters, request body, and responses
        """
        method = method.upper()
        
        # Find matching endpoint
        matching = [
            e for e in all_endpoints
            if e["path"] == path and e["method"] == method
        ]
        
        if not matching:
            # Try case-insensitive path search
            matching = [
                e for e in all_endpoints
                if e["path"].lower() == path.lower() and e["method"] == method
            ]
        
        if not matching:
            return f"Endpoint {method} {path} not found."
        
        endpoint = matching[0]
        return _format_endpoint(endpoint)
    
    @mcp.tool()
    def search_api_endpoints(query: str) -> str:
        """Search for API endpoints by keyword in path, summary, or description.
        
        Args:
            query: Search term to find matching endpoints
        
        Returns:
            List of matching endpoints with basic information
        """
        query_lower = query.lower()
        matching = [
            e for e in all_endpoints
            if query_lower in e["path"].lower()
            or query_lower in e["summary"].lower()
            or query_lower in e["description"].lower()
            or any(query_lower in tag.lower() for tag in e["tags"])
        ]
        
        if not matching:
            return f"No endpoints found matching '{query}'."
        
        # Format output
        lines = [f"Found {len(matching)} endpoint(s) matching '{query}':\n"]
        for ep in matching:
            lines.append(f"{ep['method']:6} {ep['path']}")
            if ep["summary"]:
                lines.append(f"        {ep['summary']}")
            lines.append("")
        
        return "\n".join(lines)
    
    logger.info("Registered %d API endpoints from OpenAPI spec", len(all_endpoints))
